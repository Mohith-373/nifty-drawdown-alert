"""
Abstract interface for market data providers.

Keeping this layer abstract means the alert engine never depends on a
specific vendor (Yahoo Finance, NSE, a broker API, etc). To add a new
provider, subclass MarketDataProvider and implement the two methods below,
then point Config.market_data_provider / the factory at it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class MarketDataError(Exception):
    """Raised when a market data provider cannot return a valid quote."""


@dataclass(frozen=True)
class Quote:
    """A single price observation for the index."""
    price: float
    timestamp: datetime  # timestamp of the quote itself (exchange/vendor time)
    fetched_at: datetime  # when we retrieved it locally
    source: str


@dataclass(frozen=True)
class HistoricalHigh:
    """Result of a 52-week high lookback calculation."""
    high_value: float
    high_date: datetime
    window_start: datetime
    window_end: datetime


class MarketDataProvider(ABC):
    """Base class all market data providers must implement."""

    name: str = "base"

    @abstractmethod
    def get_current_quote(self, symbol: str) -> Quote:
        """
        Return the latest available quote for `symbol`.
        Must raise MarketDataError on failure (never return a fabricated price).
        """
        raise NotImplementedError

    @abstractmethod
    def get_52_week_high(self, symbol: str, as_of: Optional[datetime] = None) -> HistoricalHigh:
        """
        Return the highest official index value over the trailing 52 weeks
        (365 days) ending at `as_of` (defaults to now), including the current
        trading day when appropriate.
        Must raise MarketDataError on failure.
        """
        raise NotImplementedError
