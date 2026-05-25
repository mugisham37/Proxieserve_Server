"""ARQ worker entrypoint."""

from __future__ import annotations

from arq import run_worker
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.notifier import EmailNotification, SmsNotification, StubNotifier

settings = get_settings()
notifier = StubNotifier()


async def send_email_job(ctx: dict[str, object], *, to: str, subject: str, body: str) -> None:
    await notifier.send_email(EmailNotification(to=to, subject=subject, body=body))


async def send_sms_job(ctx: dict[str, object], *, to: str, body: str) -> None:
    await notifier.send_sms(SmsNotification(to=to, body=body))


class WorkerSettings:
    functions = [send_email_job, send_sms_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)


if __name__ == "__main__":
    run_worker(WorkerSettings)  # type: ignore[arg-type]
