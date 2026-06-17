"""Pydantic schemas for the services module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateServiceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    category: str
    short_description: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    is_featured: bool = False
    step2_title: str | None = None
    step2_lede: str | None = None


class UpdateServiceRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    short_description: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    is_featured: bool | None = None
    step2_title: str | None = None
    step2_lede: str | None = None


class ServiceStepInput(BaseModel):
    step_number: int = Field(ge=1)
    title: str
    description: str | None = None


class DocumentRequirementInput(BaseModel):
    key: str
    label: str
    description: str | None = None
    doc_type: str
    is_required: bool = True
    max_size_mb: int = Field(default=10, ge=1, le=50)
    allowed_mime_types: list[str]
    sort_order: int = 0


class FormFieldOptionInput(BaseModel):
    value: str
    label: str
    description: str | None = None


class FormFieldInput(BaseModel):
    field_key: str
    label: str
    field_type: str
    help_text: str | None = None
    is_required: bool = True
    options: list[FormFieldOptionInput] | None = None
    conditional_on_field: str | None = None
    conditional_on_value: str | None = None
    sort_order: int = 0
    max_length: int | None = None
    placeholder: str | None = None
    card_id: str | None = None
    card_title: str | None = None


class UpdatePricingTierRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    platform_fee: int | None = None
    government_fee: int | None = None
    eta_business_days: int | None = None
    features: list[str] | None = None
    is_available: bool | None = None


class UpdateServiceStatusRequest(BaseModel):
    status: str


class ServiceStepResponse(BaseModel):
    step_number: int
    title: str
    description: str | None = None

    model_config = {"from_attributes": True}


class DocumentRequirementResponse(BaseModel):
    key: str
    label: str
    description: str | None = None
    doc_type: str
    is_required: bool
    max_size_mb: int
    allowed_mime_types: list[str]
    sort_order: int

    model_config = {"from_attributes": True}


class FormFieldOptionResponse(BaseModel):
    value: str
    label: str
    description: str | None = None


class FormFieldResponse(BaseModel):
    id: str
    label: str
    type: str
    required: bool = False
    optional: bool = False
    help: str | None = None
    options: list[FormFieldOptionResponse] | None = None
    conditional: dict[str, object] | None = None
    placeholder: str | None = None
    maxLength: int | None = None


class AppCardResponse(BaseModel):
    id: str
    title: str
    fields: list[FormFieldResponse]


class ApplicationConfigResponse(BaseModel):
    step2Title: str
    step2Lede: str
    cards: list[AppCardResponse]


class PricingTierResponse(BaseModel):
    tier: str
    label: str
    fee: int
    governmentFee: int
    eta: str
    etaBusinessDays: int
    includes: list[str]
    isAvailable: bool

    model_config = {"from_attributes": True}


class ServiceSummaryResponse(BaseModel):
    service_id: str
    slug: str
    name: str
    category: str
    short_description: str | None = None
    color: str | None = None
    icon: str | None = None
    status: str
    version: int
    is_featured: bool
    pricing_tiers: list[PricingTierResponse]

    model_config = {"from_attributes": True}


class ServiceDetailResponse(BaseModel):
    service_id: str
    slug: str
    name: str
    category: str
    short_description: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    status: str
    version: int
    is_featured: bool
    created_at: datetime
    updated_at: datetime
    steps: list[ServiceStepResponse]
    requirements: list[DocumentRequirementResponse]
    pricing_tiers: list[PricingTierResponse]
    application_config: ApplicationConfigResponse | None = None

    model_config = {"from_attributes": True}


class CreateServiceResponse(BaseModel):
    service_id: str
    slug: str
    status: str


class ServiceListResponse(BaseModel):
    services: list[ServiceSummaryResponse]
