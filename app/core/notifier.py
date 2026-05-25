"""Notification interfaces and stub implementations."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger


@dataclass(slots=True)
class EmailNotification:
    to: str
    subject: str
    body: str


@dataclass(slots=True)
class SmsNotification:
    to: str
    body: str


class StubNotifier:
    """Logs outbound notifications instead of calling a real provider."""

    def __init__(self) -> None:
        self.logger = get_logger("notifier")

    async def send_email(self, notification: EmailNotification) -> None:
        self.logger.info(
            "send_email_stub",
            to=notification.to,
            subject=notification.subject,
        )

    async def send_sms(self, notification: SmsNotification) -> None:
        self.logger.info("send_sms_stub", to=notification.to)
