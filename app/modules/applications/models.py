"""SQLAlchemy models for applications."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_client_id", "client_id"),
        Index("ix_applications_assigned_agent_id", "assigned_agent_id"),
        Index("ix_applications_status", "status"),
        Index("ix_applications_service_id", "service_id"),
        Index("ix_applications_submitted_at", "submitted_at"),
    )

    application_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.service_id"), nullable=False
    )
    service_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    client_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    assigned_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    personal_info: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    service_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    payment_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submission_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application", lazy="raise", order_by="ApplicationStatusHistory.created_at"
    )
    assignment_history: Mapped[list["ApplicationAssignmentHistory"]] = relationship(
        back_populates="application", lazy="raise", order_by="ApplicationAssignmentHistory.created_at"
    )


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"
    __table_args__ = (Index("ix_app_status_history_application_id", "application_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    changed_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    application: Mapped[Application] = relationship(back_populates="status_history", lazy="raise")


class ApplicationAssignmentHistory(Base):
    __tablename__ = "application_assignment_history"
    __table_args__ = (Index("ix_app_assignment_history_application_id", "application_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False
    )
    previous_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    new_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    performed_by: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    performed_by_role: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    application: Mapped[Application] = relationship(
        back_populates="assignment_history", lazy="raise"
    )
