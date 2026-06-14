"""ARQ worker entrypoint."""

from __future__ import annotations

from arq import run_worker
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.email import SmtpEmailNotifier
from app.core.logging import get_logger
from app.core.notifier import EmailNotification, SmsNotification, StubNotifier

logger = get_logger("worker")


def _build_notifier() -> SmtpEmailNotifier | StubNotifier:
    settings = get_settings()
    if settings.smtp_username and settings.smtp_password:
        logger.info("email_notifier_smtp", host=settings.smtp_host, port=settings.smtp_port)
        return SmtpEmailNotifier(settings)
    logger.warning("email_notifier_stub", reason="SMTP_USERNAME/SMTP_PASSWORD not configured")
    return StubNotifier()


async def send_email_job(ctx: dict[str, object], *, to: str, subject: str, body: str) -> None:
    notifier = _build_notifier()
    await notifier.send_email(EmailNotification(to=to, subject=subject, body=body))


async def send_sms_job(ctx: dict[str, object], *, to: str, body: str) -> None:
    settings = get_settings()
    notifier: SmtpEmailNotifier | StubNotifier = (
        SmtpEmailNotifier(settings) if settings.smtp_username else StubNotifier()
    )
    await notifier.send_sms(SmsNotification(to=to, body=body))


class WorkerSettings:
    functions = [send_email_job, send_sms_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)


if __name__ == "__main__":
    run_worker(WorkerSettings)  # type: ignore[arg-type]
