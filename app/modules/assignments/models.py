"""SQLAlchemy models for agent settings and skills."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AgentSettings(Base):
    __tablename__ = "agent_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    accepting_cases: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_case_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notification_new_case: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notification_client_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notification_sla_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notification_daily_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AgentServiceSkill(Base):
    __tablename__ = "agent_service_skills"
    __table_args__ = (
        UniqueConstraint("agent_id", "service_category", name="uq_agent_service_skills_agent_category"),
        Index("ix_agent_service_skills_agent_id", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    service_category: Mapped[str] = mapped_column(String(64), nullable=False)
    proficiency_level: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
