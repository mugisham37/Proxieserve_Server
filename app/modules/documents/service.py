"""Business logic for application documents."""

from __future__ import annotations

from collections.abc import AsyncIterator

import aiofiles
import filetype
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    ApplicationAccessForbiddenError,
    ApplicationNotFoundError,
    DocumentAccessForbiddenError,
    DocumentNotFoundError,
    DocumentTypeNotAllowedError,
    FileTooLargeError,
    ValidationError,
)
from app.core.jobs import JobQueueManager
from app.core.security import generate_id
from app.core.storage import get_storage
from app.modules.applications.constants import CLIENT_CANCELLABLE
from app.modules.applications.repository import ApplicationsRepository
from app.modules.documents.models import ApplicationDocument
from app.modules.documents.repository import DocumentsRepository
from app.modules.documents.schemas import DocumentListResponse, DocumentResponse, UpdateQcRequest
from app.modules.services.repository import ServicesRepository


class DocumentsService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        job_queue: JobQueueManager | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.job_queue = job_queue
        self.repo = DocumentsRepository(session)
        self.apps_repo = ApplicationsRepository(session)
        self.services_repo = ServicesRepository(session)
        self.storage = get_storage(settings)

    async def upload_document(
        self,
        *,
        code: str,
        requirement_key: str,
        upload_file: UploadFile,
        user_id: str,
        user_role: str,
        check_ownership: bool = True,
        check_assignment: bool = False,
    ) -> DocumentResponse:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        if check_ownership and app.client_id != user_id:
            raise ApplicationAccessForbiddenError(code=code)
        if check_assignment and app.assigned_agent_id != user_id:
            raise ApplicationAccessForbiddenError(code=code)
        service = await self.services_repo.get_by_id(app.service_id, load_nested=True)
        if service is None:
            raise ApplicationNotFoundError()
        requirement = next(
            (r for r in service.document_requirements if r.key == requirement_key),
            None,
        )
        if requirement is None:
            raise ValidationError(
                message="Unknown document requirement key.",
                fields=["requirement_key"],
            )
        max_bytes = requirement.max_size_mb * 1024 * 1024
        document_id = generate_id("doc")
        relative_path = f"applications/{app.application_id}/documents/{document_id}/{upload_file.filename}"
        total_written = 0

        async def chunk_stream() -> AsyncIterator[bytes]:
            nonlocal total_written
            while True:
                chunk = await upload_file.read(65536)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_bytes:
                    raise FileTooLargeError(max_bytes=max_bytes)
                yield chunk

        try:
            await self.storage.save_file(stream=chunk_stream(), relative_path=relative_path)
        except FileTooLargeError:
            await self.storage.delete_file(relative_path)
            raise

        absolute_path = await self.storage.open_file(relative_path)
        async with aiofiles.open(absolute_path, "rb") as handle:
            header = await handle.read(261)
        kind = filetype.guess(header)
        detected_mime = kind.mime if kind else "application/octet-stream"
        if detected_mime not in requirement.allowed_mime_types:
            await self.storage.delete_file(relative_path)
            raise DocumentTypeNotAllowedError(
                detected_type=detected_mime,
                allowed_types=requirement.allowed_mime_types,
            )

        existing = await self.repo.get_active_by_requirement(app.application_id, requirement_key)
        version = 1
        if existing is not None:
            version = existing.version + 1
            existing.is_active = False

        doc = await self.repo.create_document(
            document_id=document_id,
            application_id=app.application_id,
            requirement_key=requirement_key,
            original_filename=upload_file.filename or "upload",
            storage_path=relative_path,
            mime_type=detected_mime,
            file_size_bytes=total_written,
            uploaded_by=user_id,
            uploaded_by_role=user_role,
            version=version,
            qc_status="pending",
            is_active=True,
        )
        if existing is not None:
            existing.replaced_by = doc.document_id
        await self.session.commit()
        if self.job_queue:
            await self.job_queue.enqueue("document_qc_job", document_id=doc.document_id)
        return DocumentResponse.model_validate(doc)

    async def list_client_documents(self, *, code: str, client_id: str) -> DocumentListResponse:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        if app.client_id != client_id:
            raise ApplicationAccessForbiddenError(code=code)
        docs = await self.repo.list_by_application(app.application_id)
        return DocumentListResponse(
            documents=[DocumentResponse.model_validate(d) for d in docs]
        )

    async def list_case_documents(self, *, code: str, agent_id: str) -> DocumentListResponse:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        if app.assigned_agent_id != agent_id:
            raise ApplicationAccessForbiddenError(code=code)
        docs = await self.repo.list_all_by_application(app.application_id)
        return DocumentListResponse(
            documents=[DocumentResponse.model_validate(d) for d in docs]
        )

    async def get_document_for_download(
        self,
        *,
        document_id: str,
        user_id: str,
        user_role: str,
    ) -> tuple[ApplicationDocument, str]:
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError()
        app = await self.apps_repo.get_by_id(doc.application_id)
        if app is None:
            raise DocumentNotFoundError()
        if user_role == "client" and app.client_id != user_id:
            raise DocumentAccessForbiddenError()
        if user_role == "staff:agent" and app.assigned_agent_id != user_id:
            raise DocumentAccessForbiddenError()
        if user_role not in {"client", "staff:agent", "staff:admin"}:
            raise DocumentAccessForbiddenError()
        absolute = await self.storage.open_file(doc.storage_path)
        return doc, absolute

    async def update_qc(
        self,
        *,
        code: str,
        document_id: str,
        agent_id: str,
        payload: UpdateQcRequest,
    ) -> DocumentResponse:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        if app.assigned_agent_id != agent_id:
            raise ApplicationAccessForbiddenError(code=code)
        doc = await self.repo.get_by_id(document_id)
        if doc is None or doc.application_id != app.application_id:
            raise DocumentNotFoundError()
        if payload.qc_status not in {"pending", "pass", "warn", "fail"}:
            raise ValidationError(message="Invalid QC status.", fields=["qc_status"])
        doc.qc_status = payload.qc_status
        doc.qc_notes = payload.qc_notes
        await self.session.commit()
        return DocumentResponse.model_validate(doc)

    async def deactivate_document(
        self,
        *,
        code: str,
        document_id: str,
        client_id: str,
    ) -> None:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        if app.client_id != client_id:
            raise ApplicationAccessForbiddenError(code=code)
        if app.status not in CLIENT_CANCELLABLE | {"awaiting_client"}:
            raise ValidationError(message="Documents cannot be removed in the current status.")
        doc = await self.repo.get_by_id(document_id)
        if doc is None or doc.application_id != app.application_id:
            raise DocumentNotFoundError()
        doc.is_active = False
        await self.session.commit()
