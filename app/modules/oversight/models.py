"""Application escalation model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationEscalation(Base):
    __tablename__ = "application_escalations"
    __table_args__ = (
        Index("ix_application_escalations_application_id", "application_id"),
        Index("ix_application_escalations_oversight_status", "oversight_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.application_id"), nullable=False
    )
    escalated_by: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    oversight_status: Mapped[str] = mapped_column(String(32), nullable=False, default="escalated")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
