"""
Central configuration for the NIFTY 50 Drawdown Alert System.

All configuration is loaded from environment variables (via a .env file in
development). This module is the single source of truth for config values so
that no other module reads os.environ directly.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nifty_alert.config")


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if not val:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        logger.warning("Invalid value for %s: '%s' — using default %s", name, val, default)
        return default


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if not val:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        logger.warning("Invalid value for %s: '%s' — using default %s", name, val, default)
        return default


def _parse_thresholds(raw: str) -> List[float]:
    try:
        return sorted(float(x.strip()) for x in raw.split(",") if x.strip())
    except (ValueError, TypeError) as e:
        logger.warning("Invalid DRAWDOWN_THRESHOLDS: '%s' — using defaults. Error: %s", raw, e)
        return [10, 15, 20, 25, 30, 35, 40, 45, 50]


@dataclass
class Config:
    market_data_provider: str = os.getenv("MARKET_DATA_PROVIDER", "yfinance")
    nifty_ticker_symbol: str = os.getenv("NIFTY_TICKER_SYMBOL", "^NSEI")

    drawdown_thresholds: List[float] = field(
        default_factory=lambda: _parse_thresholds(
            os.getenv("DRAWDOWN_THRESHOLDS", "10,15,20,25,30,35,40,45,50")
        )
    )
    rearm_buffer_pct: float = _get_float("REARM_BUFFER_PCT", 2.0)

    poll_interval_seconds: int = _get_int("POLL_INTERVAL_SECONDS", 60)
    max_price_staleness_seconds: int = _get_int("MAX_PRICE_STALENESS_SECONDS", 900)

    market_open_time: str = os.getenv("MARKET_OPEN_TIME", "09:15")
    market_close_time: str = os.getenv("MARKET_CLOSE_TIME", "15:30")
    market_timezone: str = os.getenv("MARKET_TIMEZONE", "Asia/Kolkata")
    nse_holiday_file: str = os.getenv("NSE_HOLIDAY_FILE", "config/nse_holidays.json")

    database_path: str = os.getenv("DATABASE_PATH", "data/nifty_alerts.db")

    enable_telegram: bool = _get_bool("ENABLE_TELEGRAM_NOTIFIER", True)
    enable_email: bool = _get_bool("ENABLE_EMAIL_NOTIFIER", False)
    enable_sms: bool = _get_bool("ENABLE_SMS_NOTIFIER", False)
    enable_push: bool = _get_bool("ENABLE_PUSH_NOTIFIER", False)

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_chat_id_2: str = os.getenv("TELEGRAM_CHAT_ID_2", "")

    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = _get_int("SMTP_PORT", 587)
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")

    sms_api_key: str = os.getenv("SMS_PROVIDER_API_KEY", "")
    sms_to_number: str = os.getenv("SMS_TO_NUMBER", "")
    push_api_key: str = os.getenv("PUSH_PROVIDER_API_KEY", "")
    push_target_token: str = os.getenv("PUSH_TARGET_TOKEN", "")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/app.log")

    def validate(self) -> List[str]:
        """Return list of validation warnings. Empty = all good."""
        warnings = []
        if not self.telegram_bot_token:
            warnings.append("TELEGRAM_BOT_TOKEN is not set — Telegram alerts will not work")
        if self.enable_telegram and not self.telegram_chat_id:
            warnings.append("TELEGRAM_CHAT_ID is not set — Telegram alerts will not be delivered")
        if self.enable_email and not self.smtp_username:
            warnings.append("SMTP_USERNAME is not set — Email alerts will not work")
        if not self.drawdown_thresholds:
            warnings.append("DRAWDOWN_THRESHOLDS is empty — no alerts will fire")
        if self.poll_interval_seconds < 10:
            warnings.append("POLL_INTERVAL_SECONDS is very low (<10) — may cause rate limiting")
        return warnings

    def load_holidays(self) -> List[str]:
        """Load the NSE holiday list. Returns [] if file is missing."""
        if not os.path.exists(self.nse_holiday_file):
            return []
        try:
            with open(self.nse_holiday_file, "r") as f:
                data = json.load(f)
            return data.get("holidays", [])
        except Exception as e:
            logger.warning("Failed to load holidays from %s: %s", self.nse_holiday_file, e)
            return []


CONFIG = Config()
