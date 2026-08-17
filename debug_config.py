#!/usr/bin/env python3.14
"""Debug script to check notification configuration."""
import sys
sys.path.insert(0, '.')

from src.config import CONFIG
from src.persistence.database import Database
from src.notifications.notification_service import build_notifiers_from_config
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("debug_notifications")

logger.info("="*70)
logger.info("NOTIFICATION CONFIGURATION DEBUG")
logger.info("="*70)

logger.info(f"\nTelegram Enabled: {CONFIG.enable_telegram}")
logger.info(f"Telegram Token: {'SET' if CONFIG.telegram_bot_token else 'NOT SET'}")
logger.info(f"Telegram Chat ID: {'SET' if CONFIG.telegram_chat_id else 'NOT SET'}")

logger.info(f"\nEmail Enabled: {CONFIG.enable_email}")
logger.info(f"SMTP Host: {CONFIG.smtp_host}")
logger.info(f"SMTP Port: {CONFIG.smtp_port}")
logger.info(f"SMTP Username: {'SET' if CONFIG.smtp_username else 'NOT SET'}")
logger.info(f"Email From: {CONFIG.email_from}")
logger.info(f"Email To: {CONFIG.email_to}")

db = Database(CONFIG.database_path)
notifiers = build_notifiers_from_config(CONFIG, db)

logger.info(f"\nNotifiers created: {len(notifiers)}")
for i, notifier in enumerate(notifiers):
    logger.info(f"  {i+1}. {type(notifier).__name__}")

if len(notifiers) == 0:
    logger.warning("No notifiers configured! Check .env file.")
else:
    logger.info("Notifiers configured correctly")
