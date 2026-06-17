"""Pydantic schemas for messages."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    is_internal: bool = False
    attachments: list[str] = Field(default_factory=list)


class MessageResponse(BaseModel):
    message_id: str
    sender_id: str | None = None
    sender_role: str | None = None
    content: str
    is_internal: bool
    is_system: bool
    attachments: list[str]
    is_read_by_client: bool
    read_by_agent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
