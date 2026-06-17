"""SQLAlchemy models for service templates."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Service(Base):
    __tablename__ = "services"

    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    step2_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    step2_lede: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    steps: Mapped[list["ServiceStep"]] = relationship(
        back_populates="service", lazy="raise", order_by="ServiceStep.step_number"
    )
    document_requirements: Mapped[list["ServiceDocumentRequirement"]] = relationship(
        back_populates="service", lazy="raise", order_by="ServiceDocumentRequirement.sort_order"
    )
    form_fields: Mapped[list["ServiceFormField"]] = relationship(
        back_populates="service", lazy="raise", order_by="ServiceFormField.sort_order"
    )
    pricing_tiers: Mapped[list["ServicePricingTier"]] = relationship(
        back_populates="service", lazy="raise"
    )


class ServiceStep(Base):
    __tablename__ = "service_steps"
    __table_args__ = (
        UniqueConstraint("service_id", "step_number", name="uq_service_steps_service_step"),
        Index("ix_service_steps_service_id", "service_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.service_id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    service: Mapped[Service] = relationship(back_populates="steps", lazy="raise")


class ServiceDocumentRequirement(Base):
    __tablename__ = "service_document_requirements"
    __table_args__ = (
        UniqueConstraint("service_id", "key", name="uq_service_doc_req_service_key"),
        Index("ix_service_doc_req_service_id", "service_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.service_id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    allowed_mime_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    service: Mapped[Service] = relationship(back_populates="document_requirements", lazy="raise")


class ServiceFormField(Base):
    __tablename__ = "service_form_fields"
    __table_args__ = (
        UniqueConstraint("service_id", "field_key", name="uq_service_form_fields_service_key"),
        Index("ix_service_form_fields_service_id", "service_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.service_id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    options: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)
    conditional_on_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conditional_on_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    card_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    service: Mapped[Service] = relationship(back_populates="form_fields", lazy="raise")


class ServicePricingTier(Base):
    __tablename__ = "service_pricing_tiers"
    __table_args__ = (
        UniqueConstraint("service_id", "tier", name="uq_service_pricing_tiers_service_tier"),
        Index("ix_service_pricing_tiers_service_id", "service_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.service_id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    government_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eta_business_days: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    service: Mapped[Service] = relationship(back_populates="pricing_tiers", lazy="raise")
