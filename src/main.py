"""
Main entrypoint for the NIFTY 50 Drawdown Alert System.

Usage:
    python -m src.main

Production-grade: signal handling, graceful shutdown, network readiness,
and crash-recovery loop.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from typing import Optional

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

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logging.getLogger("nifty_alert.main").info(
        "Received %s — initiating graceful shutdown...", sig_name
    )
    _shutdown_requested = True


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


def touch_heartbeat(logger: Optional[logging.Logger] = None):
    """Touch the heartbeat file so Docker HEALTHCHECK knows the app is alive."""
    import time as _time
    path = os.getenv("HEARTBEAT_FILE", "data/heartbeat")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(str(_time.time()))
    except Exception:
        if logger:
            logger.debug("Could not write heartbeat file %s", path)


def wait_for_network(timeout_seconds: int = 120, logger: Optional[logging.Logger] = None) -> bool:
    """Wait until the network is available. Returns True if network is up."""
    import socket
    if logger is None:
        logger = logging.getLogger("nifty_alert.main")

    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=5)
            logger.info("Network is available.")
            return True
        except (OSError, socket.timeout):
            elapsed = int(time.monotonic() - start)
            logger.warning("Network not available yet (elapsed: %ds/%ds)", elapsed, timeout_seconds)
            time.sleep(5)

    logger.error("Network not available after %ds — proceeding anyway (API calls may fail).", timeout_seconds)
    return False


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

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("NIFTY 50 Drawdown Alert System starting up...")
    logger.info("PID: %d", os.getpid())

    wait_for_network(logger=logger)

    engine = None
    db = None
    max_consecutive_failures = 30
    consecutive_failures = 0

    while not _shutdown_requested:
        try:
            if engine is None:
                logger.info("Building alert engine...")
                engine = build_engine()
                logger.info("Alert engine ready. Poll interval=%ss", CONFIG.poll_interval_seconds)

            touch_heartbeat(logger)

            market_hours = MarketHours(
                open_time=CONFIG.market_open_time,
                close_time=CONFIG.market_close_time,
                timezone_name=CONFIG.market_timezone,
                holidays=CONFIG.load_holidays(),
            )

            if market_hours.is_market_open():
                result = engine.run_once()
                consecutive_failures = 0
                logger.debug("Cycle result: %s", result)
            else:
                logger.debug("Market closed (%s) — skipping cycle", market_hours.next_check_reason())

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received — shutting down.")
            break
        except Exception:
            consecutive_failures += 1
            logger.exception(
                "Unhandled exception in main loop (consecutive: %d/%d)",
                consecutive_failures,
                max_consecutive_failures,
            )
            if consecutive_failures >= max_consecutive_failures:
                logger.critical(
                    "Too many consecutive failures (%d). Rebuilding engine from scratch.",
                    consecutive_failures,
                )
                try:
                    if engine and hasattr(engine, '_db') and engine._db:
                        engine._db.close()
                except Exception:
                    pass
                engine = None
                consecutive_failures = 0
                time.sleep(30)
                continue

        # Sleep in small increments so shutdown signal can interrupt
        sleep_until = time.monotonic() + CONFIG.poll_interval_seconds
        while time.monotonic() < sleep_until and not _shutdown_requested:
            time.sleep(1)

    # Graceful cleanup
    logger.info("Shutting down gracefully...")
    try:
        if engine and hasattr(engine, '_db') and engine._db:
            engine._db.close()
            logger.info("Database connection closed.")
    except Exception:
        logger.exception("Error closing database during shutdown.")
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    run_forever()
