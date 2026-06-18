"""Global platform settings singleton model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default="global")
    accept_new_apps: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    guest_apps: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_retention_months: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    enforce_2fa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    ip_allowlist: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
