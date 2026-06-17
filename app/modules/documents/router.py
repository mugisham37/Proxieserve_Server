"""HTTP routes for application documents."""

from __future__ import annotations

from collections.abc import AsyncIterator

import aiofiles
from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import (
    REQUIRE_AGENT,
    REQUIRE_CLIENT,
    require_access_payload,
)
from app.modules.documents.schemas import DocumentListResponse, DocumentResponse, UpdateQcRequest
from app.modules.documents.service import DocumentsService

client_router = APIRouter(prefix="/api/applications", tags=["documents"])
agent_router = APIRouter(prefix="/api/agent/cases", tags=["agent-documents"])
download_router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_documents_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> DocumentsService:
    return DocumentsService(session=session, settings=settings, job_queue=job_queue)


@client_router.post(
    "/{code}/documents",
    response_model=ApiResponse[DocumentResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("client-upload-document", 20, 60))],
)
async def upload_client_document(
    code: str,
    requirement_key: str = Form(...),
    file: UploadFile = ...,
    token: dict[str, object] = Depends(require_access_payload),
    service: DocumentsService = Depends(_get_documents_service),
) -> ApiResponse[DocumentResponse]:
    data = await service.upload_document(
        code=code,
        requirement_key=requirement_key,
        upload_file=file,
        user_id=str(token["user_id"]),
        user_role=str(token["role"]),
        check_ownership=True,
    )
    return success_response(message="Document uploaded.", data=data)


@client_router.get(
    "/{code}/documents",
    response_model=ApiResponse[DocumentListResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("client-list-documents", 60, 60))],
)
async def list_client_documents(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: DocumentsService = Depends(_get_documents_service),
) -> ApiResponse[DocumentListResponse]:
    data = await service.list_client_documents(code=code, client_id=str(token["user_id"]))
    return success_response(message="Documents retrieved.", data=data)


@client_router.delete(
    "/{code}/documents/{document_id}",
    response_model=ApiResponse[None],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("client-delete-document", 20, 60))],
)
async def deactivate_client_document(
    code: str,
    document_id: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: DocumentsService = Depends(_get_documents_service),
) -> ApiResponse[None]:
    await service.deactivate_document(
        code=code,
        document_id=document_id,
        client_id=str(token["user_id"]),
    )
    return success_response(message="Document removed.", data=None)


@agent_router.post(
    "/{code}/documents",
    response_model=ApiResponse[DocumentResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-upload-document", 20, 60))],
)
async def upload_agent_document(
    code: str,
    requirement_key: str = Form(...),
    file: UploadFile = ...,
    token: dict[str, object] = Depends(require_access_payload),
    service: DocumentsService = Depends(_get_documents_service),
) -> ApiResponse[DocumentResponse]:
    data = await service.upload_document(
        code=code,
        requirement_key=requirement_key,
        upload_file=file,
        user_id=str(token["user_id"]),
        user_role=str(token["role"]),
        check_ownership=False,
        check_assignment=True,
    )
    return success_response(message="Document uploaded.", data=data)


@agent_router.patch(
    "/{code}/documents/{document_id}/qc",
    response_model=ApiResponse[DocumentResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-update-qc", 30, 60))],
)
async def update_document_qc(
    code: str,
    document_id: str,
    payload: UpdateQcRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: DocumentsService = Depends(_get_documents_service),
) -> ApiResponse[DocumentResponse]:
    data = await service.update_qc(
        code=code,
        document_id=document_id,
        agent_id=str(token["user_id"]),
        payload=payload,
    )
    return success_response(message="QC status updated.", data=data)


@download_router.get(
    "/{document_id}",
    dependencies=[Depends(rate_limit("document-download", 60, 60))],
)
async def download_document(
    document_id: str,
    inline: bool = False,
    token: dict[str, object] = Depends(require_access_payload),
    service: DocumentsService = Depends(_get_documents_service),
) -> StreamingResponse:
    doc, absolute_path = await service.get_document_for_download(
        document_id=document_id,
        user_id=str(token["user_id"]),
        user_role=str(token["role"]),
    )
    disposition = "inline" if inline else "attachment"

    async def file_iterator() -> AsyncIterator[bytes]:
        async with aiofiles.open(absolute_path, "rb") as handle:
            while chunk := await handle.read(65536):
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{doc.original_filename}"',
            "Content-Length": str(doc.file_size_bytes),
        },
    )
