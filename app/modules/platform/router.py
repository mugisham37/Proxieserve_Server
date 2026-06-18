"""Platform settings HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import REQUIRE_ADMIN, require_access_payload
from app.modules.platform.schemas import AdminSettingsResponse, UpdateAdminSettingsRequest
from app.modules.platform.service import PlatformService

router = APIRouter(prefix="/api/admin", tags=["admin-settings"])


def _get_service(session: AsyncSession = Depends(get_db_session)) -> PlatformService:
    return PlatformService(session)


@router.get(
    "/settings",
    response_model=ApiResponse[AdminSettingsResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-get-settings", 30, 60))],
)
async def get_settings(
    service: PlatformService = Depends(_get_service),
) -> ApiResponse[AdminSettingsResponse]:
    data = await service.get_settings()
    return success_response(message="Settings retrieved.", data=data)


@router.patch(
    "/settings",
    response_model=ApiResponse[AdminSettingsResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-update-settings", 20, 60))],
)
async def update_settings(
    payload: UpdateAdminSettingsRequest,
    request: Request,
    token: dict[str, object] = Depends(require_access_payload),
    service: PlatformService = Depends(_get_service),
) -> ApiResponse[AdminSettingsResponse]:
    data = await service.update_settings(
        admin_id=str(token["user_id"]),
        payload=payload,
        ip_address=request.client.host if request.client else None,
    )
    return success_response(message="Settings updated.", data=data)
