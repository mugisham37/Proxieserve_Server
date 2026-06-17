"""Pydantic schemas for documents."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    document_id: str
    application_id: str
    requirement_key: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    uploaded_by: str
    uploaded_by_role: str
    version: int
    qc_status: str
    qc_notes: dict[str, object] | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class UpdateQcRequest(BaseModel):
    qc_status: str
    qc_notes: dict[str, object] | None = None
