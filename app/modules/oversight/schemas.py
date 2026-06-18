"""Oversight DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OversightCaseResponse(BaseModel):
    code: str
    service: str
    agent: str
    client: str
    status: str
    issue: str | None = None


class OversightCaseListResponse(BaseModel):
    cases: list[OversightCaseResponse]


class EscalateCaseRequest(BaseModel):
    reason: str = Field(min_length=10)


class ResolveCaseRequest(BaseModel):
    resolution_note: str | None = None
