"""
Yahoo Finance implementation of MarketDataProvider.

Notes on data quality:
- Yahoo Finance data for Indian indices is typically delayed by ~15 minutes,
  NOT real-time. This provider is intended as a free, dependency-light
  default. For real-time / production trading-grade data, swap in a paid
  vendor or broker API (e.g. NSE official feed, Kite Connect, Upstox,
  Alpha Vantage, Twelve Data) by implementing MarketDataProvider.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pytz

from src.data_provider.base import (
    MarketDataProvider,
    MarketDataError,
    Quote,
    HistoricalHigh,
)

IST = pytz.timezone("Asia/Kolkata")


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self):
        # Imported lazily so the rest of the codebase can be unit-tested
        # without the yfinance/pandas dependency chain being mandatory.
        try:
            import yfinance as yf  # noqa: F401
        except ImportError as e:
            raise MarketDataError(
                "yfinance package is not installed. Run `pip install yfinance`."
            ) from e
        self._yf = yf

    def get_current_quote(self, symbol: str) -> Quote:
        try:
            ticker = self._yf.Ticker(symbol)
            # 1-minute bars over the last day is the most reliable way to get
            # a recent price + timestamp from yfinance for indices.
            hist = ticker.history(period="1d", interval="1m")
            if hist is None or hist.empty:
                raise MarketDataError(f"No intraday data returned for {symbol}")

            last_row = hist.iloc[-1]
            price = float(last_row["Close"])
            ts = hist.index[-1].to_pydatetime()
            if ts.tzinfo is None:
                ts = pytz.utc.localize(ts)
            ts = ts.astimezone(IST)

            if price is None or price <= 0:
                raise MarketDataError(f"Invalid price returned for {symbol}: {price}")

            return Quote(
                price=price,
                timestamp=ts,
                fetched_at=datetime.now(IST),
                source=self.name,
            )
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Failed to fetch quote for {symbol}: {e}") from e

    def get_52_week_high(self, symbol: str, as_of: Optional[datetime] = None) -> HistoricalHigh:
        try:
            as_of = as_of or datetime.now(IST)
            window_start = as_of - timedelta(days=365)

            ticker = self._yf.Ticker(symbol)
            hist = ticker.history(start=window_start.strftime("%Y-%m-%d"),
                                   end=(as_of + timedelta(days=1)).strftime("%Y-%m-%d"),
                                   interval="1d")
            if hist is None or hist.empty:
                raise MarketDataError(f"No historical data returned for {symbol}")

            # Use the daily High column - the official intraday high for that
            # trading day - never a constituent stock's high.
            high_value = float(hist["High"].max())
            high_idx = hist["High"].idxmax()
            high_date = high_idx.to_pydatetime()
            if high_date.tzinfo is None:
                high_date = IST.localize(high_date)

            if high_value <= 0:
                raise MarketDataError(f"Invalid 52-week high computed for {symbol}: {high_value}")

            return HistoricalHigh(
                high_value=high_value,
                high_date=high_date,
                window_start=window_start,
                window_end=as_of,
            )
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Failed to compute 52-week high for {symbol}: {e}") from e
