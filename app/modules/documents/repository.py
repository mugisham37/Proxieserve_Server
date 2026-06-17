"""Persistence helpers for documents."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import ApplicationDocument


class DocumentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_document(self, **kwargs: object) -> ApplicationDocument:
        doc = ApplicationDocument(**kwargs)
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_by_id(self, document_id: str) -> ApplicationDocument | None:
        return await self.session.get(ApplicationDocument, document_id)

    async def get_active_by_requirement(
        self,
        application_id: str,
        requirement_key: str,
    ) -> ApplicationDocument | None:
        return cast(
            ApplicationDocument | None,
            await self.session.scalar(
                select(ApplicationDocument).where(
                    ApplicationDocument.application_id == application_id,
                    ApplicationDocument.requirement_key == requirement_key,
                    ApplicationDocument.is_active.is_(True),
                )
            ),
        )

    async def list_by_application(self, application_id: str) -> list[ApplicationDocument]:
        query = (
            select(ApplicationDocument)
            .where(
                ApplicationDocument.application_id == application_id,
                ApplicationDocument.is_active.is_(True),
            )
            .order_by(ApplicationDocument.created_at.asc())
        )
        return list(await self.session.scalars(query))

    async def list_all_by_application(self, application_id: str) -> list[ApplicationDocument]:
        query = (
            select(ApplicationDocument)
            .where(ApplicationDocument.application_id == application_id)
            .order_by(ApplicationDocument.created_at.asc())
        )
        return list(await self.session.scalars(query))
