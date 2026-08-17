from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from src.notifications.base import Notifier, NotificationResult


class EmailNotifier(Notifier):
    channel_name = "email"

    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str,
                 email_from: str, email_to: str, timeout_seconds: int = 15):
        self._host = smtp_host
        self._port = smtp_port
        self._username = username
        self._password = password
        self._from = email_from
        self._to = email_to
        self._timeout = timeout_seconds

    def send(self, message: str, subject: str = "NIFTY 50 Drawdown Alert") -> NotificationResult:
        if not all([self._host, self._username, self._password, self._from, self._to]):
            return NotificationResult(self.channel_name, False, "Email not configured")
        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = self._from
            msg["To"] = self._to

            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
                server.starttls()
                server.login(self._username, self._password)
                server.sendmail(self._from, [self._to], msg.as_string())
            return NotificationResult(self.channel_name, True, "sent")
        except Exception as e:
            return NotificationResult(self.channel_name, False, str(e))
