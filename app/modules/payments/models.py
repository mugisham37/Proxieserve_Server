"""Payment transaction model."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_application_id", "application_id"),
        Index("ix_payments_status", "status"),
    )

    payment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.application_id", ondelete="RESTRICT"), nullable=False
    )
    amount_rwf: Mapped[int] = mapped_column(Integer, nullable=False)
    government_fee_rwf: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_fee_rwf: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.18"))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RWF")
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    receipt_number: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    card_brand: Mapped[str | None] = mapped_column(String(16), nullable=True)
    masked_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
