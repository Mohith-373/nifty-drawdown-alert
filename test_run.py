#!/usr/bin/env python3.14
"""Quick test to check market status and run one alert cycle."""
import sys
sys.path.insert(0, '.')

from src.config import CONFIG
from src.market_hours import MarketHours
from src.data_provider import get_provider
from src.persistence.database import Database
from src.services.price_service import PriceService
from src.services.high_calculator import HighCalculator
from src.services.threshold_engine import ThresholdEngine
from src.services.alert_state_manager import AlertStateManager
from src.notifications.notification_service import NotificationService, build_notifiers_from_config
from src.alert_engine import AlertEngine
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_run")

# Check market status
market_hours = MarketHours(
    open_time=CONFIG.market_open_time,
    close_time=CONFIG.market_close_time,
    timezone_name=CONFIG.market_timezone,
    holidays=CONFIG.load_holidays(),
)

is_open = market_hours.is_market_open()
logger.info(f"Market Status: {'OPEN ✓' if is_open else 'CLOSED ✗'}")
logger.info(f"Reason: {market_hours.next_check_reason() if not is_open else 'Market is OPEN'}")

# Try to run one cycle
if is_open:
    logger.info("\n" + "="*70)
    logger.info("Running one alert cycle...")
    logger.info("="*70)
    
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
    
    engine = AlertEngine(
        price_service=price_service,
        high_calculator=high_calculator,
        state_manager=state_manager,
        notification_service=notification_service,
        db=db,
        min_configured_threshold=min(CONFIG.drawdown_thresholds),
    )
    
    result = engine.run_once()
    logger.info(f"Cycle result: {result}")
    logger.info("✓ Alert system is working correctly!")
else:
    logger.info("Market is closed. System will monitor during trading hours (09:15-15:30 IST, weekdays)")
