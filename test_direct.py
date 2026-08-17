#!/usr/bin/env python3.14
"""Send test notification directly using credentials from .env."""
import sys
import os
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

from src.notifications.telegram_notifier import TelegramNotifier
from src.notifications.email_notifier import EmailNotifier
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_test_direct")

telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
smtp_host = os.getenv("SMTP_HOST", "")
smtp_port = int(os.getenv("SMTP_PORT", "587"))
smtp_user = os.getenv("SMTP_USERNAME", "")
smtp_pass = os.getenv("SMTP_PASSWORD", "")
email_from = os.getenv("EMAIL_FROM", "")
email_to = os.getenv("EMAIL_TO", "")

logger.info("="*70)
logger.info("SENDING TEST NOTIFICATION")
logger.info("="*70)

test_message = """TEST ALERT - NIFTY 50 Alert System

Your notification setup is WORKING!

Current Price: 22,500
52-Week High: 23,000
Drawdown: 2.2%

This confirms your Telegram and Email alerts are configured correctly.
You will receive real alerts when NIFTY falls below thresholds.

Time: """ + str(__import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"))

logger.info(f"\nTest message:\n{test_message}\n")
logger.info("Sending to both channels...\n")

results = []

logger.info("Sending Telegram notification...")
try:
    telegram = TelegramNotifier(telegram_token, telegram_chat_id)
    result = telegram.send(test_message, subject="NIFTY 50 TEST")
    if result.success:
        logger.info(f"  Telegram: SUCCESS")
        results.append(True)
    else:
        logger.warning(f"  Telegram: FAILED - {result.detail}")
        results.append(False)
except Exception as e:
    logger.error(f"  Telegram ERROR: {e}")
    results.append(False)

logger.info("Sending Email notification...")
try:
    email = EmailNotifier(smtp_host, smtp_port, smtp_user, smtp_pass, email_from, email_to)
    result = email.send(test_message, subject="NIFTY 50 TEST ALERT")
    if result.success:
        logger.info(f"  Email: SUCCESS")
        results.append(True)
    else:
        logger.warning(f"  Email: FAILED - {result.detail}")
        results.append(False)
except Exception as e:
    logger.error(f"  Email ERROR: {e}")
    results.append(False)

logger.info("\n" + "="*70)
if all(results):
    logger.info("BOTH NOTIFICATIONS SENT SUCCESSFULLY!")
elif any(results):
    logger.warning(f"Partial success: {sum(results)}/2 channels working")
else:
    logger.error("NO CHANNELS WORKING - Check .env credentials")
logger.info("="*70)
