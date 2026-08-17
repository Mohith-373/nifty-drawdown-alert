"""
Indian market hours / trading-day logic.

Handles: normal open/close window, weekends, and NSE holidays (loaded from
config/nse_holidays.json). This module has no side effects - it just answers
"is the market open at time X" given a config and holiday list.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import List

import pytz


class MarketHours:
    def __init__(self, open_time: str, close_time: str, timezone_name: str, holidays: List[str]):
        self._tz = pytz.timezone(timezone_name)
        self._open_time = self._parse_time(open_time)
        self._close_time = self._parse_time(close_time)
        self._holidays = set(holidays)

    @staticmethod
    def _parse_time(value: str) -> time:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))

    def is_trading_day(self, dt: datetime) -> bool:
        local = self._to_local(dt)
        if local.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if local.strftime("%Y-%m-%d") in self._holidays:
            return False
        return True

    def is_market_open(self, dt: datetime = None) -> bool:
        dt = dt or datetime.now(self._tz)
        local = self._to_local(dt)
        if not self.is_trading_day(local):
            return False
        return self._open_time <= local.time() <= self._close_time

    def _to_local(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = self._tz.localize(dt)
        return dt.astimezone(self._tz)

    def next_check_reason(self, dt: datetime = None) -> str:
        """Human-readable reason the market is currently closed, for logging."""
        dt = dt or datetime.now(self._tz)
        local = self._to_local(dt)
        if local.weekday() >= 5:
            return "weekend"
        if local.strftime("%Y-%m-%d") in self._holidays:
            return "NSE holiday"
        if local.time() < self._open_time:
            return "before market open"
        if local.time() > self._close_time:
            return "after market close"
        return "market open"
