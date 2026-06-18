"""Payment background jobs."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.database import db_manager
from app.core.logging import get_logger
from app.core.payments import get_payment_gateway
from app.modules.payments.repository import PaymentsRepository
from app.modules.payments.service import PaymentsService

logger = get_logger("payment_jobs")


async def payment_timeout_job(ctx: dict[str, object], *, payment_id: str) -> None:
    if db_manager.session_factory is None:
        raise RuntimeError("DatabaseManager is not configured")
    settings = get_settings()
    gateway = get_payment_gateway(settings)
    async with db_manager.session_factory() as session:
        service = PaymentsService(session=session, gateway=gateway, job_queue=None)
        payment = await service.repo.get_by_id(payment_id)
        if payment is None or payment.status != "processing":
            return
        status, _ = await gateway.check_transaction_status(payment.provider_transaction_id or "")
        if status == "paid":
            await service.confirm_payment(payment_id)
            await session.commit()
            return
        payment.status = "timed_out"
        payment.updated_at = datetime.now(UTC)
        await session.commit()
        logger.info("payment_timed_out", payment_id=payment_id)


async def payment_card_confirm_job(ctx: dict[str, object], *, payment_id: str) -> None:
    if db_manager.session_factory is None:
        raise RuntimeError("DatabaseManager is not configured")
    settings = get_settings()
    gateway = get_payment_gateway(settings)
    async with db_manager.session_factory() as session:
        service = PaymentsService(session=session, gateway=gateway, job_queue=None)
        await service.confirm_payment(payment_id)
        await session.commit()
