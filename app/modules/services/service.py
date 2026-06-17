"""Business logic for service templates."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceNotFoundError, ServiceSlugConflictError, ValidationError
from app.core.security import generate_id
from app.modules.services.constants import (
    DOC_TYPES,
    FIELD_TYPES,
    PRICING_TIERS,
    SERVICE_CATEGORIES,
    SERVICE_STATUSES,
    VALID_SERVICE_STATUS_TRANSITIONS,
)
from app.modules.services.models import Service, ServicePricingTier
from app.modules.services.repository import ServicesRepository
from app.modules.services.schemas import (
    AppCardResponse,
    ApplicationConfigResponse,
    CreateServiceRequest,
    CreateServiceResponse,
    DocumentRequirementInput,
    DocumentRequirementResponse,
    FormFieldInput,
    FormFieldOptionResponse,
    FormFieldResponse,
    PricingTierResponse,
    ServiceDetailResponse,
    ServiceListResponse,
    ServiceStepInput,
    ServiceStepResponse,
    ServiceSummaryResponse,
    UpdatePricingTierRequest,
    UpdateServiceRequest,
)


def _field_type_to_frontend(field_type: str) -> str:
    if field_type == "radio_card":
        return "radio-card"
    return field_type


def _field_type_from_frontend(field_type: str) -> str:
    if field_type == "radio-card":
        return "radio_card"
    return field_type


def _build_application_config(service: Service) -> ApplicationConfigResponse | None:
    if not service.form_fields:
        return None
    cards_map: dict[str, AppCardResponse] = {}
    card_order: list[str] = []
    for field in sorted(service.form_fields, key=lambda item: item.sort_order):
        card_id = field.card_id or "default"
        if card_id not in cards_map:
            cards_map[card_id] = AppCardResponse(
                id=card_id,
                title=field.card_title or "Details",
                fields=[],
            )
            card_order.append(card_id)
        options = None
        if field.options:
            options = [
                FormFieldOptionResponse(
                    value=opt["value"],
                    label=opt["label"],
                    description=opt.get("description"),
                )
                for opt in field.options
            ]
        conditional = None
        if field.conditional_on_field and field.conditional_on_value:
            conditional = {
                "field": field.conditional_on_field,
                "values": [field.conditional_on_value],
            }
        cards_map[card_id].fields.append(
            FormFieldResponse(
                id=field.field_key,
                label=field.label,
                type=_field_type_to_frontend(field.field_type),
                required=field.is_required,
                optional=not field.is_required,
                help=field.help_text,
                options=options,
                conditional=conditional,
                placeholder=field.placeholder,
                maxLength=field.max_length,
            )
        )
    return ApplicationConfigResponse(
        step2Title=service.step2_title or "Service details",
        step2Lede=service.step2_lede or "Please provide the required information.",
        cards=[cards_map[cid] for cid in card_order],
    )


def _pricing_tier_response(tier: ServicePricingTier) -> PricingTierResponse:
    return PricingTierResponse(
        tier=tier.tier,
        label=tier.display_name,
        fee=tier.platform_fee,
        governmentFee=tier.government_fee,
        eta=f"{tier.eta_business_days} business days",
        etaBusinessDays=tier.eta_business_days,
        includes=tier.features,
        isAvailable=tier.is_available,
    )


def _service_detail_response(service: Service) -> ServiceDetailResponse:
    return ServiceDetailResponse(
        service_id=service.service_id,
        slug=service.slug,
        name=service.name,
        category=service.category,
        short_description=service.short_description,
        description=service.description,
        color=service.color,
        icon=service.icon,
        status=service.status,
        version=service.version,
        is_featured=service.is_featured,
        created_at=service.created_at,
        updated_at=service.updated_at,
        steps=[
            ServiceStepResponse(
                step_number=step.step_number,
                title=step.title,
                description=step.description,
            )
            for step in sorted(service.steps, key=lambda s: s.step_number)
        ],
        requirements=[
            DocumentRequirementResponse(
                key=req.key,
                label=req.label,
                description=req.description,
                doc_type=req.doc_type,
                is_required=req.is_required,
                max_size_mb=req.max_size_mb,
                allowed_mime_types=req.allowed_mime_types,
                sort_order=req.sort_order,
            )
            for req in sorted(service.document_requirements, key=lambda r: r.sort_order)
        ],
        pricing_tiers=[_pricing_tier_response(t) for t in service.pricing_tiers],
        application_config=_build_application_config(service),
    )


class ServicesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ServicesRepository(session)

    async def create_service(
        self,
        payload: CreateServiceRequest,
        *,
        created_by: str,
    ) -> CreateServiceResponse:
        if payload.category not in SERVICE_CATEGORIES:
            raise ValidationError(message="Invalid service category.", fields=["category"])
        if await self.repo.slug_exists(payload.slug):
            raise ServiceSlugConflictError()
        service_id = generate_id("svc")
        service = await self.repo.create_service(
            service_id=service_id,
            slug=payload.slug,
            name=payload.name,
            category=payload.category,
            short_description=payload.short_description,
            description=payload.description,
            color=payload.color,
            icon=payload.icon,
            status="draft",
            is_featured=payload.is_featured,
            step2_title=payload.step2_title,
            step2_lede=payload.step2_lede,
            created_by=created_by,
        )
        for tier_name, display, fee, gov_fee, eta, features in _default_pricing_tiers():
            await self.repo.create_pricing_tier(
                id=generate_id("spt"),
                service_id=service.service_id,
                tier=tier_name,
                display_name=display,
                platform_fee=fee,
                government_fee=gov_fee,
                eta_business_days=eta,
                features=features,
                is_available=True,
            )
        await self.session.commit()
        return CreateServiceResponse(
            service_id=service.service_id,
            slug=service.slug,
            status=service.status,
        )

    async def update_service(self, slug: str, payload: UpdateServiceRequest) -> ServiceDetailResponse:
        service = await self._get_service_or_raise(slug, load_nested=True)
        if payload.category is not None and payload.category not in SERVICE_CATEGORIES:
            raise ValidationError(message="Invalid service category.", fields=["category"])
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(service, field, value)
        await self.session.flush()
        await self.session.commit()
        return _service_detail_response(service)

    async def set_steps(self, slug: str, steps: list[ServiceStepInput]) -> ServiceDetailResponse:
        service = await self._get_service_or_raise(slug, load_nested=True)
        step_data = [
            {
                "id": generate_id("sst"),
                "step_number": step.step_number,
                "title": step.title,
                "description": step.description,
            }
            for step in steps
        ]
        await self.repo.replace_steps(service.service_id, step_data)
        service.version += 1
        await self.session.flush()
        service = await self._get_service_or_raise(slug, load_nested=True)
        await self.session.commit()
        return _service_detail_response(service)

    async def set_document_requirements(
        self,
        slug: str,
        requirements: list[DocumentRequirementInput],
    ) -> ServiceDetailResponse:
        service = await self._get_service_or_raise(slug, load_nested=True)
        req_data = []
        for req in requirements:
            if req.doc_type not in DOC_TYPES:
                raise ValidationError(message="Invalid document type.", fields=["doc_type"])
            req_data.append(
                {
                    "id": generate_id("sdr"),
                    "key": req.key,
                    "label": req.label,
                    "description": req.description,
                    "doc_type": req.doc_type,
                    "is_required": req.is_required,
                    "max_size_mb": req.max_size_mb,
                    "allowed_mime_types": req.allowed_mime_types,
                    "sort_order": req.sort_order,
                }
            )
        await self.repo.replace_document_requirements(service.service_id, req_data)
        service.version += 1
        await self.session.flush()
        service = await self._get_service_or_raise(slug, load_nested=True)
        await self.session.commit()
        return _service_detail_response(service)

    async def set_form_fields(
        self,
        slug: str,
        fields: list[FormFieldInput],
    ) -> ServiceDetailResponse:
        service = await self._get_service_or_raise(slug, load_nested=True)
        field_data = []
        for field in fields:
            if field.field_type not in FIELD_TYPES:
                raise ValidationError(message="Invalid field type.", fields=["field_type"])
            options = None
            if field.options:
                options = [opt.model_dump() for opt in field.options]
            field_data.append(
                {
                    "id": generate_id("sff"),
                    "field_key": field.field_key,
                    "label": field.label,
                    "field_type": field.field_type,
                    "help_text": field.help_text,
                    "is_required": field.is_required,
                    "options": options,
                    "conditional_on_field": field.conditional_on_field,
                    "conditional_on_value": field.conditional_on_value,
                    "sort_order": field.sort_order,
                    "max_length": field.max_length,
                    "placeholder": field.placeholder,
                    "card_id": field.card_id,
                    "card_title": field.card_title,
                }
            )
        await self.repo.replace_form_fields(service.service_id, field_data)
        service.version += 1
        await self.session.flush()
        service = await self._get_service_or_raise(slug, load_nested=True)
        await self.session.commit()
        return _service_detail_response(service)

    async def update_pricing_tier(
        self,
        slug: str,
        tier_name: str,
        payload: UpdatePricingTierRequest,
    ) -> ServiceDetailResponse:
        if tier_name not in PRICING_TIERS:
            raise ValidationError(message="Invalid pricing tier.", fields=["tier"])
        service = await self._get_service_or_raise(slug, load_nested=False)
        tier = await self.repo.get_pricing_tier(service.service_id, tier_name)
        if tier is None:
            raise ServiceNotFoundError()
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(tier, field, value)
        await self.session.flush()
        service = await self._get_service_or_raise(slug, load_nested=True)
        await self.session.commit()
        return _service_detail_response(service)

    async def update_status(self, slug: str, new_status: str) -> ServiceDetailResponse:
        if new_status not in SERVICE_STATUSES:
            raise ValidationError(message="Invalid service status.", fields=["status"])
        service = await self._get_service_or_raise(slug, load_nested=True)
        allowed = VALID_SERVICE_STATUS_TRANSITIONS.get(service.status, set())
        if new_status not in allowed and new_status != service.status:
            raise ValidationError(
                message=f"Cannot transition service from '{service.status}' to '{new_status}'.",
                fields=["status"],
            )
        service.status = new_status
        await self.session.flush()
        await self.session.commit()
        return _service_detail_response(service)

    async def list_public_services(self) -> ServiceListResponse:
        services = await self.repo.list_services(status="active", load_nested=True)
        return ServiceListResponse(
            services=[
                ServiceSummaryResponse(
                    service_id=s.service_id,
                    slug=s.slug,
                    name=s.name,
                    category=s.category,
                    short_description=s.short_description,
                    color=s.color,
                    icon=s.icon,
                    status=s.status,
                    version=s.version,
                    is_featured=s.is_featured,
                    pricing_tiers=[
                        _pricing_tier_response(t) for t in s.pricing_tiers if t.is_available
                    ],
                )
                for s in services
            ]
        )

    async def get_public_service(self, slug: str) -> ServiceDetailResponse:
        service = await self.repo.get_by_slug(slug, load_nested=True)
        if service is None or service.status != "active":
            raise ServiceNotFoundError()
        return _service_detail_response(service)

    async def list_admin_services(self) -> ServiceListResponse:
        services = await self.repo.list_services(load_nested=True)
        return ServiceListResponse(
            services=[
                ServiceSummaryResponse(
                    service_id=s.service_id,
                    slug=s.slug,
                    name=s.name,
                    category=s.category,
                    short_description=s.short_description,
                    color=s.color,
                    icon=s.icon,
                    status=s.status,
                    version=s.version,
                    is_featured=s.is_featured,
                    pricing_tiers=[_pricing_tier_response(t) for t in s.pricing_tiers],
                )
                for s in services
            ]
        )

    async def get_admin_service(self, slug: str) -> ServiceDetailResponse:
        service = await self._get_service_or_raise(slug, load_nested=True)
        return _service_detail_response(service)

    async def _get_service_or_raise(self, slug: str, *, load_nested: bool) -> Service:
        service = await self.repo.get_by_slug(slug, load_nested=load_nested)
        if service is None:
            raise ServiceNotFoundError()
        return service


def _default_pricing_tiers() -> list[tuple[str, str, int, int, int, list[str]]]:
    return [
        ("standard", "Standard", 0, 0, 5, ["Standard processing"]),
        ("express", "Express", 0, 0, 3, ["Priority processing"]),
        ("urgent", "Urgent", 0, 0, 1, ["Same-day processing"]),
    ]
