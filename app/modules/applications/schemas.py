"""DTOs for the applications module."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.documents.schemas import DocumentResponse
from app.modules.messages.schemas import MessageResponse


class ApplicationLookupData(BaseModel):
    code: str
    serviceName: str
    submittedDate: str
    status: str


class ApplicationClaimRequest(BaseModel):
    code: str = Field(min_length=14, max_length=15)
    phone: str = Field(min_length=9)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.match(r"^PRX-\d{4}-\d{5}$", value):
            raise ValueError("Invalid PRX code")
        return value


class ApplicationClaimData(BaseModel):
    claimed: bool = True


class PersonalInfoInput(BaseModel):
    fullName: str
    nationalId: str
    dob: str
    phone: str
    email: str
    whatsapp: bool = False
    language: str = "en"
    consent: bool = True


class SubmitApplicationRequest(BaseModel):
    service_slug: str
    tier: str
    personal_info: PersonalInfoInput
    service_data: dict[str, object] = Field(default_factory=dict)


class SubmitApplicationResponse(BaseModel):
    application_id: str
    code: str
    service_name: str
    tier: str
    payment_required: bool


class ApplicationSummaryResponse(BaseModel):
    application_id: str
    code: str
    service_name: str
    service_slug: str
    status: str
    tier: str
    submitted_at: datetime
    payment_status: str


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationSummaryResponse]


class StatusHistoryResponse(BaseModel):
    status: str
    changed_by: str | None = None
    changed_by_role: str | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplicationDetailResponse(BaseModel):
    application_id: str
    code: str
    service_name: str
    service_slug: str
    tier: str
    status: str
    personal_info: dict[str, object]
    service_data: dict[str, object]
    payment_status: str
    payment_amount: int | None = None
    submitted_at: datetime
    assigned_agent_id: str | None = None
    status_history: list[StatusHistoryResponse] = Field(default_factory=list)
    documents: list[DocumentResponse] = Field(default_factory=list)
    messages: list[MessageResponse] = Field(default_factory=list)


class CancelApplicationRequest(BaseModel):
    reason: str | None = None


class UpdateStatusRequest(BaseModel):
    status: str
    note: str | None = None
    rejection_reason: str | None = None


class TrackerStepResponse(BaseModel):
    step_number: int
    title: str
    status: str


class TrackerResponse(BaseModel):
    code: str
    service_name: str
    status: str
    current_step_number: int | None = None
    current_step_title: str | None = None
    estimated_completion: str | None = None
    submitted_at: datetime
    updated_at: datetime


class AdminApplicationListResponse(BaseModel):
    applications: list[ApplicationSummaryResponse]
    total: int
    offset: int
    limit: int


class AgentCaseSummary(BaseModel):
    code: str
    service_name: str
    client_name: str
    status: str
    tier: str
    submitted_at: datetime
    sla_state: str
    unread_messages: int = 0


class AgentCaseListResponse(BaseModel):
    cases: list[AgentCaseSummary]


class AnalyticsResponse(BaseModel):
    by_status: dict[str, int]
    by_service: list[dict[str, object]]
    total_applications: int
    sla_compliance_rate: float
    payment_pending_count: int
