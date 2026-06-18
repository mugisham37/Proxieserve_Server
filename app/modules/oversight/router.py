"""Oversight HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import REQUIRE_ADMIN, require_access_payload
from app.modules.oversight.schemas import (
    EscalateCaseRequest,
    OversightCaseListResponse,
    ResolveCaseRequest,
)
from app.modules.oversight.service import OversightService

router = APIRouter(prefix="/api/admin/oversight", tags=["admin-oversight"])


def _get_service(session: AsyncSession = Depends(get_db_session)) -> OversightService:
    return OversightService(session)


@router.get(
    "/cases",
    response_model=ApiResponse[OversightCaseListResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-oversight", 60, 60))],
)
async def list_oversight_cases(
    tab: str = Query(default="all"),
    service: OversightService = Depends(_get_service),
) -> ApiResponse[OversightCaseListResponse]:
    data = await service.list_cases(tab=tab)
    return success_response(message="Oversight cases retrieved.", data=data)


@router.patch(
    "/cases/{code}/escalate",
    response_model=ApiResponse[dict[str, bool]],
    dependencies=[REQUIRE_ADMIN],
)
async def escalate_case(
    code: str,
    payload: EscalateCaseRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: OversightService = Depends(_get_service),
) -> ApiResponse[dict[str, bool]]:
    await service.escalate_case(
        code=code,
        admin_id=str(token["user_id"]),
        payload=payload,
    )
    return success_response(message="Case escalated.", data={"ok": True})


@router.patch(
    "/cases/{code}/resolve",
    response_model=ApiResponse[dict[str, bool]],
    dependencies=[REQUIRE_ADMIN],
)
async def resolve_case(
    code: str,
    payload: ResolveCaseRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: OversightService = Depends(_get_service),
) -> ApiResponse[dict[str, bool]]:
    await service.resolve_case(
        code=code,
        admin_id=str(token["user_id"]),
        payload=payload,
    )
    return success_response(message="Case resolved.", data={"ok": True})
