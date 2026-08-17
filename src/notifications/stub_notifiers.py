"""
SMS and Push notifier stubs.

These are intentionally NOT wired to a real vendor - Indian SMS (e.g.
MSG91, Twilio) and Push (e.g. FCM, OneSignal) each require their own account
setup and API contract. Implement `send()` with the vendor's SDK/HTTP API
when ready; the rest of the system (NotificationService, alert flow) already
supports them via the ENABLE_SMS_NOTIFIER / ENABLE_PUSH_NOTIFIER toggles.
"""
from __future__ import annotations

from src.notifications.base import Notifier, NotificationResult


class SmsNotifier(Notifier):
    channel_name = "sms"

    def __init__(self, api_key: str, to_number: str):
        self._api_key = api_key
        self._to_number = to_number

    def send(self, message: str, subject: str = "") -> NotificationResult:
        if not self._api_key or not self._to_number:
            return NotificationResult(self.channel_name, False, "SMS not configured")
        # TODO: integrate real SMS provider (e.g. Twilio, MSG91) here.
        return NotificationResult(self.channel_name, False, "SMS provider not implemented")


class PushNotifier(Notifier):
    channel_name = "push"

    def __init__(self, api_key: str, target_token: str):
        self._api_key = api_key
        self._target_token = target_token

    def send(self, message: str, subject: str = "") -> NotificationResult:
        if not self._api_key or not self._target_token:
            return NotificationResult(self.channel_name, False, "Push not configured")
        # TODO: integrate real push provider (e.g. FCM, OneSignal) here.
        return NotificationResult(self.channel_name, False, "Push provider not implemented")
