"""Send backtest results using credentials from .env."""
import sys
import os
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

from src.notifications.telegram_notifier import TelegramNotifier
from src.notifications.email_notifier import EmailNotifier
from src.config import CONFIG
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest_notify")
