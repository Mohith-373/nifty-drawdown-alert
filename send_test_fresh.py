#!/usr/bin/env python3.14
"""Send test notification - fresh env load."""
import sys
import os

# Force reload of environment variables
if 'PYTHONDONTWRITEBYTECODE' not in os.environ:
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

sys.path.insert(0, '.')

# Import and reload dotenv FIRST
from dotenv import load_dotenv
dotenv_path = '.env'
load_dotenv(dotenv_path, override=True)  # Force override of existing env vars

# Now import config
from src.config import CONFIG
from src.persistence.database import Database
from src.notifications.notification_service import build_notifiers_from_config
from src.notifications.base import Notifier
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("send_test")

logger.info("="*70)
logger.info("SENDING TEST NOTIFICATION TO YOUR ACCOUNTS")
logger.info("="*70)

# Verify config
logger.info(f"\n✓ Configuration loaded:")
logger.info(f"  Telegram: {CONFIG.enable_telegram} (Token: {'SET' if CONFIG.telegram_bot_token else 'NOT SET'})")
logger.info(f"  Email: {CONFIG.enable_email} (To: {CONFIG.email_to})")

# Build notifiers
db = Database(CONFIG.database_path)
notifiers = build_notifiers_from_config(CONFIG, db)

logger.info(f"\n✓ Notifiers initialized: {len(notifiers)} channel(s)")
for notifier in notifiers:
    logger.info(f"  - {type(notifier).__name__}")

if len(notifiers) == 0:
    logger.error("\n✗ ERROR: No notifiers found! Check .env file.")
    sys.exit(1)

# Create test message
test_message = """🧪 TEST ALERT - NIFTY 50 Alert System

Your notification setup is WORKING! ✓

Current Price: ₹22,500
52-Week High: ₹23,000
Drawdown: 2.2%

This is a test message sent at: """ + str(__import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

logger.info(f"\nTest message:\n{test_message}\n")
logger.info("Sending notifications...\n")

# Send via each notifier
success_count = 0
for notifier in notifiers:
    try:
        result = notifier.send(test_message, subject="NIFTY 50 - TEST NOTIFICATION")
        if result.success:
            logger.info(f"✓ {result.channel}: SUCCESS")
            success_count += 1
        else:
            logger.warning(f"✗ {result.channel}: FAILED - {result.detail}")
    except Exception as e:
        logger.error(f"✗ {type(notifier).__name__}: ERROR - {e}")

logger.info("\n" + "="*70)
if success_count > 0:
    logger.info(f"✓ Test notification sent successfully to {success_count} channel(s)!")
    logger.info("\nCheck your:")
    if CONFIG.enable_telegram:
        logger.info(f"  📱 Telegram chat (ID: {CONFIG.telegram_chat_id})")
    if CONFIG.enable_email:
        logger.info(f"  📧 Email inbox ({CONFIG.email_to})")
    logger.info("\nThe alert system will send real notifications when market opens Monday!")
else:
    logger.error("✗ Failed to send test notifications. Check credentials.")
logger.info("="*70)
