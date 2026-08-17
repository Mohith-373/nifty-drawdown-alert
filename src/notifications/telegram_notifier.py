from __future__ import annotations

import requests

from src.notifications.base import Notifier, NotificationResult


class TelegramNotifier(Notifier):
    channel_name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 10):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout_seconds

    def send(self, message: str, subject: str = "") -> NotificationResult:
        if not self._bot_token or not self._chat_id:
            return NotificationResult(self.channel_name, False, "Telegram not configured")
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self._chat_id, "text": message},
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                return NotificationResult(self.channel_name, True, "sent")
            return NotificationResult(self.channel_name, False, f"HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            return NotificationResult(self.channel_name, False, str(e))
