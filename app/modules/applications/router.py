"""HTTP routes for the applications seam."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.api import ApiResponse, success_response
from app.core.ratelimit import rate_limit
from app.modules.applications.schemas import (
    ApplicationClaimData,
    ApplicationClaimRequest,
    ApplicationLookupData,
)
from app.modules.applications.service import ApplicationsService
from app.modules.auth.dependencies import REQUIRE_CLIENT

router = APIRouter(prefix="/api/applications", tags=["applications"])
service = ApplicationsService()


@router.get(
    "/lookup",
    response_model=ApiResponse[ApplicationLookupData],
    dependencies=[Depends(rate_limit("applications-lookup", 20, 60))],
)
async def lookup_application(code: str) -> ApiResponse[ApplicationLookupData]:
    result = await service.lookup_by_code(code)
    return success_response(
        message="Application found.",
        data=ApplicationLookupData(
            code=result.code,
            serviceName=result.serviceName,
            submittedDate=result.submittedDate,
            status=result.status,
        ),
    )


@router.post(
    "/claim",
    response_model=ApiResponse[ApplicationClaimData],
    dependencies=[Depends(rate_limit("applications-claim", 10, 60)), REQUIRE_CLIENT],
)
async def claim_application(payload: ApplicationClaimRequest) -> ApiResponse[ApplicationClaimData]:
    await service.claim(code=payload.code, phone=payload.phone)
    return success_response(message="Application claim accepted.", data=ApplicationClaimData())
