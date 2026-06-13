"""Pydantic schemas for the admin module."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator


class CreateAgentRequest(BaseModel):
    name: str
    email: EmailStr
    temporary_password: str | None = None

    @field_validator("name")
    @classmethod
    def name_min_length(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return v.strip()


class CreateAgentResponse(BaseModel):
    agent_id: str
    name: str
    email: str
    role: str = "staff:agent"
    created_at: str
    invite_sent: bool


class AgentListItem(BaseModel):
    agent_id: str
    name: str
    email: str
    is_active: bool
    twofa_enabled: bool
    created_at: str


class AgentListResponse(BaseModel):
    agents: list[AgentListItem]


class UpdateAgentRequest(BaseModel):
    is_active: bool | None = None
    reset_password: bool | None = None
    force_2fa_reset: bool | None = None


class UpdateAgentResponse(BaseModel):
    agent_id: str
    updated: list[str]
