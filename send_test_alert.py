#!/usr/bin/env python3.14
"""Send a test notification to verify Telegram and Email are working."""
import sys
sys.path.insert(0, '.')

from src.config import CONFIG
from src.persistence.database import Database
from src.notifications.notification_service import NotificationService, build_notifiers_from_config
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_notification")

logger.info("="*70)
logger.info("SENDING TEST NOTIFICATION")
logger.info("="*70)

db = Database(CONFIG.database_path)
notifiers = build_notifiers_from_config(CONFIG, db)
notification_service = NotificationService(notifiers, db)

test_message = """TEST NOTIFICATION - NIFTY 50 ALERT SYSTEM

Current Price: 22,500
52-Week High: 23,000
Drawdown: 2.2%

This is a TEST alert to verify your Telegram and Email
notifications are working correctly.

Your system is ready for market hours!"""

logger.info("\nSending test alert...")

try:
    results = notification_service.notify_all(
        alert_id=0,
        message=test_message,
        subject="NIFTY 50 ALERT - TEST"
    )

    logger.info("\n" + "="*70)
    logger.info("RESULTS:")
    logger.info("="*70)

    for result in results:
        status = "SUCCESS" if result.success else "FAILED"
        logger.info(f"{status} - {result.channel}")
        if result.detail:
            logger.info(f"  Detail: {result.detail}")

    logger.info("\nCheck your Telegram and Email for the test alert.")
    logger.info("="*70)

except Exception as e:
    logger.error(f"Error sending notification: {e}")
    import traceback
    traceback.print_exc()
