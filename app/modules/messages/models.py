"""SQLAlchemy models for application messages."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationMessage(Base):
    __tablename__ = "application_messages"
    __table_args__ = (Index("ix_application_messages_application_id", "application_id"),)

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    sender_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_read_by_client: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_by_agent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    application: Mapped["Application"] = relationship(lazy="raise")  # type: ignore[name-defined]  # noqa: F821
