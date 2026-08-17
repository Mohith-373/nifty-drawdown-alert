#!/usr/bin/env python3.14
"""Test notification with .env path detection."""
import sys
import os

sys.path.insert(0, '.')

env_path = os.path.join(os.path.dirname(__file__), '.env')

print(f"Loading .env from: {env_path}")
print(f"File exists: {os.path.exists(env_path)}")

from dotenv import load_dotenv
load_dotenv(env_path, override=True)

print("\n=== ENVIRONMENT VARIABLES (after load_dotenv) ===")
for key in ['ENABLE_TELEGRAM_NOTIFIER', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
            'ENABLE_EMAIL_NOTIFIER', 'SMTP_USERNAME', 'EMAIL_FROM', 'EMAIL_TO']:
    val = os.getenv(key, "NOT SET")
    if len(val) > 10:
        val = val[:5] + "..." + val[-3:]
    print(f"{key}={val}")

print("\n=== IMPORTING CONFIG ===")
from src.config import CONFIG
from src.persistence.database import Database
from src.notifications.notification_service import build_notifiers_from_config

print(f"Telegram enabled in CONFIG: {CONFIG.enable_telegram}")
print(f"Email enabled in CONFIG: {CONFIG.enable_email}")

db = Database(CONFIG.database_path)
notifiers = build_notifiers_from_config(CONFIG, db)
print(f"\nNotifiers created: {len(notifiers)}")
for n in notifiers:
    print(f"  - {type(n).__name__}")
