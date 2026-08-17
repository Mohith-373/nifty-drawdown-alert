"""
Main entrypoint for the NIFTY 50 Drawdown Alert System.

Usage:
    python -m src.main
"""
from __future__ import annotations

import logging
import os
import time

from src.config import CONFIG
from src.data_provider import get_provider
from src.persistence.database import Database
from src.services.price_service import PriceService
from src.services.high_calculator import HighCalculator
from src.services.threshold_engine import ThresholdEngine
from src.services.alert_state_manager import AlertStateManager
from src.notifications.notification_service import NotificationService, build_notifiers_from_config
from src.market_hours import MarketHours
from src.alert_engine import AlertEngine


def setup_logging():
    os.makedirs(os.path.dirname(CONFIG.log_file) or ".", exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(CONFIG.log_file),
            logging.StreamHandler(),
        ],
    )


def build_engine() -> AlertEngine:
    db = Database(CONFIG.database_path)
    provider = get_provider(CONFIG.market_data_provider)

    price_service = PriceService(
        provider=provider,
        symbol=CONFIG.nifty_ticker_symbol,
        max_staleness_seconds=CONFIG.max_price_staleness_seconds,
    )
    high_calculator = HighCalculator(provider=provider, db=db, symbol=CONFIG.nifty_ticker_symbol)

    threshold_engine = ThresholdEngine(
        configured_thresholds=CONFIG.drawdown_thresholds,
        rearm_buffer_pct=CONFIG.rearm_buffer_pct,
    )
    state_manager = AlertStateManager(db, threshold_engine, CONFIG.drawdown_thresholds)

    notifiers = build_notifiers_from_config(CONFIG, db)
    notification_service = NotificationService(notifiers, db)

    return AlertEngine(
        price_service=price_service,
        high_calculator=high_calculator,
        state_manager=state_manager,
        notification_service=notification_service,
        db=db,
        min_configured_threshold=min(CONFIG.drawdown_thresholds),
    )


def run_forever():
    setup_logging()
    logger = logging.getLogger("nifty_alert.main")

    engine = build_engine()
    market_hours = MarketHours(
        open_time=CONFIG.market_open_time,
        close_time=CONFIG.market_close_time,
        timezone_name=CONFIG.market_timezone,
        holidays=CONFIG.load_holidays(),
    )

    logger.info("NIFTY 50 Drawdown Alert System starting. Poll interval=%ss", CONFIG.poll_interval_seconds)

    while True:
        if market_hours.is_market_open():
            result = engine.run_once()
            logger.debug("Cycle result: %s", result)
        else:
            logger.debug("Market closed (%s) - skipping cycle", market_hours.next_check_reason())
        time.sleep(CONFIG.poll_interval_seconds)


if __name__ == "__main__":
    run_forever()
