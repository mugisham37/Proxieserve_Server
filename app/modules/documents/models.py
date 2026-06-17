"""SQLAlchemy models for application documents."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationDocument(Base):
    __tablename__ = "application_documents"
    __table_args__ = (
        Index("ix_application_documents_application_id", "application_id"),
        Index(
            "ix_application_documents_active_req",
            "application_id",
            "requirement_key",
        ),
    )

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False
    )
    requirement_key: Mapped[str] = mapped_column(String(128), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    uploaded_by_role: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    qc_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    qc_notes: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    replaced_by: Mapped[str | None] = mapped_column(
        ForeignKey("application_documents.document_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    application: Mapped["Application"] = relationship(lazy="raise")  # type: ignore[name-defined]  # noqa: F821
