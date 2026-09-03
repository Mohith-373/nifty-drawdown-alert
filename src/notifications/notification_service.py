"""
Notification Service with retry-protected fan-out.

Individual notifier failures are caught so one channel never kills another.
"""
from __future__ import annotations

import logging
from typing import List

from src.notifications.base import Notifier, NotificationResult
from src.persistence.database import Database

logger = logging.getLogger("nifty_alert.notifications")


class NotificationService:
    def __init__(self, notifiers: List[Notifier], db: Database):
        self._notifiers = notifiers
        self._db = db

    def notify_all(self, alert_id: int, message: str, subject: str = "") -> List[NotificationResult]:
        results = []
        for notifier in self._notifiers:
            try:
                result = notifier.send(message, subject=subject)
            except Exception as exc:
                logger.exception("Notifier %s raised an exception", type(notifier).__name__)
                result = NotificationResult(
                    channel=getattr(notifier, "channel_name", type(notifier).__name__),
                    success=False,
                    detail=str(exc),
                )
            try:
                self._db.record_notification_delivery(
                    alert_id=alert_id,
                    channel=result.channel,
                    status="sent" if result.success else "failed",
                    detail=result.detail,
                )
            except Exception:
                logger.exception("Failed to record notification delivery for %s", result.channel)
            if not result.success:
                try:
                    self._db.record_error("NotificationService", f"{result.channel} failed: {result.detail}")
                except Exception:
                    pass
            results.append(result)
        return results


def build_notifiers_from_config(config, db: Database) -> List[Notifier]:
    """Factory that builds the list of active Notifier instances."""
    from src.notifications.telegram_notifier import TelegramNotifier
    from src.notifications.email_notifier import EmailNotifier
    from src.notifications.stub_notifiers import SmsNotifier, PushNotifier

    notifiers: List[Notifier] = []
    if config.enable_telegram:
        chat_ids = [cid for cid in [config.telegram_chat_id, config.telegram_chat_id_2] if cid]
        if not chat_ids:
            chat_ids = [""]
        for chat_id in chat_ids:
            notifiers.append(TelegramNotifier(config.telegram_bot_token, chat_id))
    if config.enable_email:
        notifiers.append(EmailNotifier(
            config.smtp_host, config.smtp_port, config.smtp_username,
            config.smtp_password, config.email_from, config.email_to,
        ))
    if config.enable_sms:
        notifiers.append(SmsNotifier(config.sms_api_key, config.sms_to_number))
    if config.enable_push:
        notifiers.append(PushNotifier(config.push_api_key, config.push_target_token))
    return notifiers
