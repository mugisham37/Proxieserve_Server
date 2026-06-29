"""Notification interfaces and stub implementations."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
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
        log_kwargs: dict[str, str] = {
            "to": notification.to,
            "subject": notification.subject,
        }
        settings = get_settings()
        if settings.app_env == "development":
            log_kwargs["body_preview"] = notification.body[:500]
        self.logger.info("send_email_stub", **log_kwargs)

    async def send_sms(self, notification: SmsNotification) -> None:
        log_kwargs: dict[str, str] = {"to": notification.to}
        settings = get_settings()
        if settings.app_env == "development":
            log_kwargs["body"] = notification.body
        self.logger.info("send_sms_stub", **log_kwargs)
