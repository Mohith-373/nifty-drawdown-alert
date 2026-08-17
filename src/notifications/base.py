"""
Abstract notifier interface. Every channel (Telegram, Email, SMS, Push)
implements this so the NotificationService can treat them uniformly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    success: bool
    detail: str = ""


class Notifier(ABC):
    channel_name: str = "base"

    @abstractmethod
    def send(self, message: str, subject: str = "") -> NotificationResult:
        """Send `message` over this channel. Must never raise - catch
        internally and return a NotificationResult(success=False, ...)."""
        raise NotImplementedError
