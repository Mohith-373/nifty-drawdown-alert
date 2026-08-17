"""
NIFTY 50 Price Service.

Wraps the raw MarketDataProvider with validation and staleness checks so
that no invalid or stale price can ever reach the drawdown/threshold logic.
"Never silently substitute an incorrect price" (spec sec. 8) is enforced
here: on any validation failure we raise, we never return a fallback price.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.data_provider.base import MarketDataProvider, Quote, MarketDataError


class InvalidPriceError(MarketDataError):
    pass


class StalePriceError(MarketDataError):
    pass


class PriceService:
    def __init__(self, provider: MarketDataProvider, symbol: str, max_staleness_seconds: int):
        self._provider = provider
        self._symbol = symbol
        self._max_staleness_seconds = max_staleness_seconds

    def get_validated_quote(self, now: datetime = None) -> Quote:
        quote = self._provider.get_current_quote(self._symbol)
        now = now or datetime.now(quote.timestamp.tzinfo)

        self._validate_price(quote)
        self._validate_freshness(quote, now)
        return quote

    def _validate_price(self, quote: Quote):
        if quote.price is None or quote.price <= 0:
            raise InvalidPriceError(f"Invalid NIFTY price received: {quote.price}")
        # Sanity bound: NIFTY 50 is very unlikely to ever be outside this
        # broad range; guards against garbage/misparsed data. Adjust over
        # time as the index grows.
        if not (1000 <= quote.price <= 200000):
            raise InvalidPriceError(f"NIFTY price out of plausible range: {quote.price}")

    def _validate_freshness(self, quote: Quote, now: datetime):
        age = (now - quote.timestamp).total_seconds()
        if age > self._max_staleness_seconds:
            raise StalePriceError(
                f"Quote is stale: {age:.0f}s old (max allowed {self._max_staleness_seconds}s), "
                f"quote_time={quote.timestamp.isoformat()}"
            )
        if age < -60:
            # Quote timestamped in the future (clock skew / bad data)
            raise InvalidPriceError(
                f"Quote timestamp is in the future: {quote.timestamp.isoformat()}"
            )
