"""Payment persistence."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payment


class PaymentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: object) -> Payment:
        payment = Payment(**kwargs)
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: str) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_latest_for_application(self, application_id: str) -> Payment | None:
        query = (
            select(Payment)
            .where(Payment.application_id == application_id)
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        return cast(Payment | None, await self.session.scalar(query))

    async def receipt_exists(self, receipt_number: str) -> bool:
        result = await self.session.scalar(
            select(Payment.payment_id).where(Payment.receipt_number == receipt_number)
        )
        return result is not None
