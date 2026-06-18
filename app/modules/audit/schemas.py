"""Audit log DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    actor: str
    actorType: str
    description: str
    kind: str


class AuditLogResponse(BaseModel):
    entries: list[AuditEntry]
    total: int
    has_more: bool
