"""Persistence helpers for service templates."""

from __future__ import annotations

from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.services.models import (
    Service,
    ServiceDocumentRequirement,
    ServiceFormField,
    ServicePricingTier,
    ServiceStep,
)


class ServicesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_service(self, **kwargs: object) -> Service:
        service = Service(**kwargs)
        self.session.add(service)
        await self.session.flush()
        return service

    async def get_by_slug(
        self,
        slug: str,
        *,
        load_nested: bool = False,
    ) -> Service | None:
        query = select(Service).where(Service.slug == slug)
        if load_nested:
            query = query.options(
                selectinload(Service.steps),
                selectinload(Service.document_requirements),
                selectinload(Service.form_fields),
                selectinload(Service.pricing_tiers),
            )
        return cast(Service | None, await self.session.scalar(query))

    async def get_by_id(
        self,
        service_id: str,
        *,
        load_nested: bool = False,
    ) -> Service | None:
        query = select(Service).where(Service.service_id == service_id)
        if load_nested:
            query = query.options(
                selectinload(Service.steps),
                selectinload(Service.document_requirements),
                selectinload(Service.form_fields),
                selectinload(Service.pricing_tiers),
            )
        return cast(Service | None, await self.session.scalar(query))

    async def slug_exists(self, slug: str) -> bool:
        result = await self.session.scalar(select(Service.service_id).where(Service.slug == slug))
        return result is not None

    async def list_services(
        self,
        *,
        status: str | None = None,
        load_nested: bool = False,
    ) -> list[Service]:
        query = select(Service).order_by(Service.name)
        if status is not None:
            query = query.where(Service.status == status)
        if load_nested:
            query = query.options(selectinload(Service.pricing_tiers))
        return list(await self.session.scalars(query))

    async def replace_steps(self, service_id: str, steps: list[dict[str, object]]) -> None:
        await self.session.execute(delete(ServiceStep).where(ServiceStep.service_id == service_id))
        for step_data in steps:
            self.session.add(ServiceStep(service_id=service_id, **step_data))
        await self.session.flush()

    async def replace_document_requirements(
        self,
        service_id: str,
        requirements: list[dict[str, object]],
    ) -> None:
        await self.session.execute(
            delete(ServiceDocumentRequirement).where(
                ServiceDocumentRequirement.service_id == service_id
            )
        )
        for req_data in requirements:
            self.session.add(ServiceDocumentRequirement(service_id=service_id, **req_data))
        await self.session.flush()

    async def replace_form_fields(
        self,
        service_id: str,
        fields: list[dict[str, object]],
    ) -> None:
        await self.session.execute(
            delete(ServiceFormField).where(ServiceFormField.service_id == service_id)
        )
        for field_data in fields:
            self.session.add(ServiceFormField(service_id=service_id, **field_data))
        await self.session.flush()

    async def get_pricing_tier(self, service_id: str, tier: str) -> ServicePricingTier | None:
        return cast(
            ServicePricingTier | None,
            await self.session.scalar(
                select(ServicePricingTier).where(
                    ServicePricingTier.service_id == service_id,
                    ServicePricingTier.tier == tier,
                )
            ),
        )

    async def create_pricing_tier(self, **kwargs: object) -> ServicePricingTier:
        tier = ServicePricingTier(**kwargs)
        self.session.add(tier)
        await self.session.flush()
        return tier

    async def count_services(self) -> int:
        result = await self.session.scalar(select(Service.service_id))
        if result is None:
            return 0
        services = await self.list_services()
        return len(services)
