"""
52-Week High Calculator.

Responsible ONLY for determining and persisting the rolling 52-week high of
the NIFTY 50 index itself (never a constituent stock). It never fires alerts
and never talks to notification channels - single responsibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.data_provider.base import MarketDataProvider, HistoricalHigh, MarketDataError
from src.persistence.database import Database


class HighCalculator:
    def __init__(self, provider: MarketDataProvider, db: Database, symbol: str):
        self._provider = provider
        self._db = db
        self._symbol = symbol

    def refresh(self, as_of: Optional[datetime] = None) -> HistoricalHigh:
        """
        Recompute the 52-week high from the market data provider and persist
        it if it represents a new high (or if none is stored yet).

        Returns the HistoricalHigh currently in effect (freshly computed).
        Raises MarketDataError if the provider fails - callers must NOT
        fabricate/reuse a stale high silently; they should catch this and
        fall back to the last persisted value if one exists.
        """
        fresh = self._provider.get_52_week_high(self._symbol, as_of=as_of)

        stored = self._db.get_fifty_two_week_high()
        if stored is None or fresh.high_value > stored["high_value"]:
            self._db.upsert_fifty_two_week_high(
                high_value=fresh.high_value,
                high_date=fresh.high_date.isoformat(),
                computed_at=datetime.now(timezone.utc).isoformat(),
            )
        return fresh

    def get_persisted_high(self) -> Optional[dict]:
        """Return the last persisted 52-week high, or None if never computed."""
        return self._db.get_fifty_two_week_high()

    def get_current_high_value(self, as_of: Optional[datetime] = None) -> float:
        """
        Best-effort accessor used by the main loop: try to refresh from the
        provider; on failure, fall back to the persisted value. Raises
        MarketDataError only if BOTH the live refresh fails AND there is no
        persisted value to fall back on.
        """
        try:
            fresh = self.refresh(as_of=as_of)
            return fresh.high_value
        except MarketDataError:
            stored = self.get_persisted_high()
            if stored is None:
                raise
            return stored["high_value"]
