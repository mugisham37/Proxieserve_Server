"""SMTP email delivery via aiosmtplib."""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.notifier import EmailNotification


class SmtpEmailNotifier:
    """Sends email via SMTP using aiosmtplib.

    Falls back gracefully: if ``smtp_username`` is set the connection uses
    STARTTLS (suitable for Gmail / SendGrid on port 587); otherwise it
    connects without authentication (suitable for local Mailpit on port 1025).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger("smtp-notifier")

    async def send_email(self, notification: EmailNotification) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = notification.subject
        message["From"] = self.settings.email_from
        message["To"] = notification.to
        message.attach(MIMEText(notification.body, "html", "utf-8"))

        send_kwargs: dict[str, object] = {
            "hostname": self.settings.smtp_host,
            "port": self.settings.smtp_port,
        }
        if self.settings.smtp_username and self.settings.smtp_password:
            send_kwargs["username"] = self.settings.smtp_username
            send_kwargs["password"] = self.settings.smtp_password
            send_kwargs["start_tls"] = True

        await aiosmtplib.send(message, **send_kwargs)  # type: ignore[arg-type]
        self.logger.info("email_sent", to=notification.to, subject=notification.subject)
