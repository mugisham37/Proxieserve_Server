"""Pydantic schemas for assignments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssignAgentRequest(BaseModel):
    agent_id: str
    note: str | None = None


class AgentSettingsResponse(BaseModel):
    accepting_cases: bool
    daily_case_cap: int | None = None
    notification_new_case: bool
    notification_client_reply: bool
    notification_sla_alert: bool
    notification_daily_summary: bool

    model_config = {"from_attributes": True}


class UpdateAgentSettingsRequest(BaseModel):
    accepting_cases: bool | None = None
    daily_case_cap: int | None = Field(default=None, ge=1, le=100)
    notification_new_case: bool | None = None
    notification_client_reply: bool | None = None
    notification_sla_alert: bool | None = None
    notification_daily_summary: bool | None = None


class UnassignedCaseResponse(BaseModel):
    code: str
    service_name: str
    submitted_at: str
    tier: str
    eta_business_days: int | None = None


class UnassignedQueueResponse(BaseModel):
    count: int
    cases: list[UnassignedCaseResponse]
