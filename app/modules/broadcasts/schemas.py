"""Broadcast DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateBroadcastRequest(BaseModel):
    audience_description: str
    audience_filter: dict[str, object]
    channels: list[str]
    message: str = Field(max_length=1000)
    scheduled_at: datetime | None = None


class BroadcastRecordResponse(BaseModel):
    id: str
    audience: str
    channels: list[str]
    message: str
    sentAt: str
    reach: int


class BroadcastListResponse(BaseModel):
    broadcasts: list[BroadcastRecordResponse]
