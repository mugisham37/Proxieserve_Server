"""Broadcast communication model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    audience_description: Mapped[str] = mapped_column(String(255), nullable=False)
    audience_filter: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    broadcast_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
