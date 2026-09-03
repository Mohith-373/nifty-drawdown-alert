"""
Yahoo Finance market data provider with retry and exponential backoff.

Handles transient network failures, DNS issues, rate limits, and
temporary API outages gracefully.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pytz

from src.data_provider.base import MarketDataProvider, Quote, HistoricalHigh, MarketDataError

logger = logging.getLogger("nifty_alert.data_provider")

IST = pytz.timezone("Asia/Kolkata")

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 2.0
DEFAULT_MAX_DELAY = 30.0


def _retry_with_backoff(func, max_retries=DEFAULT_MAX_RETRIES, base_delay=DEFAULT_BASE_DELAY,
                         max_delay=DEFAULT_MAX_DELAY, label="operation"):
    """Execute func with exponential backoff on failure."""
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except MarketDataError:
            raise
        except Exception as exc:
            last_exception = exc
            if attempt < max_retries:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                logger.warning(
                    "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                    label, attempt, max_retries, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "%s failed after %d attempts: %s", label, max_retries, exc
                )
    raise MarketDataError(f"{label} failed after {max_retries} attempts: {last_exception}")


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self):
        try:
            import yfinance  # noqa: F401
        except ImportError:
            raise MarketDataError(
                "yfinance is not installed. Run: pip install yfinance"
            )

    def get_current_quote(self, symbol: str) -> Quote:
        def _fetch():
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d", interval="1m")
            if hist is None or hist.empty:
                raise MarketDataError(
                    f"No intraday data returned for {symbol}"
                )

            last_row = hist.iloc[-1]
            price = float(last_row["Close"])
            if hasattr(price, "item"):
                price = price.item()

            if price <= 0:
                raise MarketDataError(f"Invalid price received: {price}")

            # Build timestamp from the index
            ts_raw = hist.index[-1]
            if hasattr(ts_raw, "to_pydatetime"):
                ts = ts_raw.to_pydatetime()
            else:
                ts = datetime.now(IST)
            if ts.tzinfo is None:
                ts = IST.localize(ts)

            now = datetime.now(IST)
            return Quote(
                price=price,
                timestamp=ts,
                fetched_at=now,
                source=self.name,
            )

        return _retry_with_backoff(_fetch, label=f"get_current_quote({symbol})")

    def get_52_week_high(self, symbol: str, as_of=None) -> HistoricalHigh:
        def _fetch():
            import yfinance as yf

            end_date = as_of or datetime.now(IST)
            start_date = end_date - timedelta(days=365)

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                                  end=end_date.strftime("%Y-%m-%d"),
                                  interval="1d")
            if hist is None or hist.empty:
                raise MarketDataError(
                    f"No historical data returned for {symbol}"
                )

            high_series = hist["High"]
            high_val = float(high_series.max())
            if hasattr(high_val, "item"):
                high_val = high_val.item()

            if high_val <= 0:
                raise MarketDataError(f"Invalid 52-week high: {high_val}")

            high_date_idx = high_series.idxmax()
            if hasattr(high_date_idx, "to_pydatetime"):
                high_date = high_date_idx.to_pydatetime()
            else:
                high_date = end_date
            if high_date.tzinfo is None:
                high_date = IST.localize(high_date)

            return HistoricalHigh(
                high_value=high_val,
                high_date=high_date,
                window_start=start_date,
                window_end=end_date,
            )

        return _retry_with_backoff(_fetch, label=f"get_52_week_high({symbol})")
