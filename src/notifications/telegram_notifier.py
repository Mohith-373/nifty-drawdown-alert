"""Telegram notification sender with retry and exponential backoff."""
from __future__ import annotations

import logging
import time

import requests

from src.notifications.base import Notifier, NotificationResult

logger = logging.getLogger("nifty_alert.notifications.telegram")


class TelegramNotifier(Notifier):
    channel_name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 15,
                 max_retries: int = 3):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    def send(self, message: str, subject: str = "") -> NotificationResult:
        if not self._bot_token or not self._chat_id:
            return NotificationResult(self.channel_name, False, "Telegram not configured")

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        last_error = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json={"chat_id": self._chat_id, "text": message},
                    timeout=self._timeout,
                )

                if resp.status_code == 200:
                    return NotificationResult(self.channel_name, True, "sent")

                if resp.status_code == 429:
                    retry_after = 5
                    try:
                        retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                    except Exception:
                        pass
                    logger.warning("Telegram rate limited, retrying in %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 500 or resp.status_code == 408:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if attempt < self._max_retries:
                        delay = min(2 ** attempt, 15)
                        logger.warning("Telegram HTTP %d (attempt %d/%d), retrying in %.1fs",
                                       resp.status_code, attempt, self._max_retries, delay)
                        time.sleep(delay)
                        continue
                    return NotificationResult(self.channel_name, False, last_error)

                return NotificationResult(
                    self.channel_name, False,
                    f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            except requests.exceptions.Timeout:
                last_error = "Request timed out"
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
            except Exception as e:
                last_error = str(e)

            if attempt < self._max_retries:
                delay = min(2 ** attempt, 15)
                logger.warning("Telegram send failed (attempt %d/%d): %s — retrying in %.1fs",
                               attempt, self._max_retries, last_error, delay)
                time.sleep(delay)

        return NotificationResult(self.channel_name, False, last_error or "All retries failed")
