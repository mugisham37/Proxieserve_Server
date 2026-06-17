"""HTTP routes for service templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import REQUIRE_ADMIN, require_access_payload
from app.modules.services.schemas import (
    CreateServiceRequest,
    CreateServiceResponse,
    DocumentRequirementInput,
    FormFieldInput,
    ServiceDetailResponse,
    ServiceListResponse,
    ServiceStepInput,
    UpdatePricingTierRequest,
    UpdateServiceRequest,
    UpdateServiceStatusRequest,
)
from app.modules.services.service import ServicesService

public_router = APIRouter(prefix="/api/services", tags=["services"])
admin_router = APIRouter(prefix="/api/admin/services", tags=["admin-services"])


def _get_services_service(
    session: AsyncSession = Depends(get_db_session),
) -> ServicesService:
    return ServicesService(session)


@public_router.get(
    "",
    response_model=ApiResponse[ServiceListResponse],
    dependencies=[Depends(rate_limit("services-list", 60, 60))],
)
async def list_services(
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceListResponse]:
    data = await service.list_public_services()
    return success_response(message="Services retrieved.", data=data)


@public_router.get(
    "/{slug}",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[Depends(rate_limit("services-detail", 60, 60))],
)
async def get_service(
    slug: str,
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.get_public_service(slug)
    return success_response(message="Service retrieved.", data=data)


@admin_router.post(
    "",
    response_model=ApiResponse[CreateServiceResponse],
    status_code=201,
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-create-service", 20, 60))],
)
async def create_service(
    payload: CreateServiceRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[CreateServiceResponse]:
    data = await service.create_service(
        payload,
        created_by=str(token["user_id"]),
    )
    return success_response(message="Service created.", data=data)


@admin_router.get(
    "",
    response_model=ApiResponse[ServiceListResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-list-services", 60, 60))],
)
async def list_admin_services(
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceListResponse]:
    data = await service.list_admin_services()
    return success_response(message="Services retrieved.", data=data)


@admin_router.get(
    "/{slug}",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-get-service", 60, 60))],
)
async def get_admin_service(
    slug: str,
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.get_admin_service(slug)
    return success_response(message="Service retrieved.", data=data)


@admin_router.patch(
    "/{slug}",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-update-service", 30, 60))],
)
async def update_service(
    slug: str,
    payload: UpdateServiceRequest,
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.update_service(slug, payload)
    return success_response(message="Service updated.", data=data)


@admin_router.post(
    "/{slug}/steps",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-set-steps", 20, 60))],
)
async def set_service_steps(
    slug: str,
    steps: list[ServiceStepInput],
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.set_steps(slug, steps)
    return success_response(message="Service steps updated.", data=data)


@admin_router.post(
    "/{slug}/document-requirements",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-set-doc-reqs", 20, 60))],
)
async def set_document_requirements(
    slug: str,
    requirements: list[DocumentRequirementInput],
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.set_document_requirements(slug, requirements)
    return success_response(message="Document requirements updated.", data=data)


@admin_router.post(
    "/{slug}/form-fields",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-set-form-fields", 20, 60))],
)
async def set_form_fields(
    slug: str,
    fields: list[FormFieldInput],
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.set_form_fields(slug, fields)
    return success_response(message="Form fields updated.", data=data)


@admin_router.patch(
    "/{slug}/pricing/{tier}",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-update-pricing", 30, 60))],
)
async def update_pricing_tier(
    slug: str,
    tier: str,
    payload: UpdatePricingTierRequest,
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.update_pricing_tier(slug, tier, payload)
    return success_response(message="Pricing tier updated.", data=data)


@admin_router.patch(
    "/{slug}/status",
    response_model=ApiResponse[ServiceDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-update-service-status", 20, 60))],
)
async def update_service_status(
    slug: str,
    payload: UpdateServiceStatusRequest,
    service: ServicesService = Depends(_get_services_service),
) -> ApiResponse[ServiceDetailResponse]:
    data = await service.update_status(slug, payload.status)
    return success_response(message="Service status updated.", data=data)
