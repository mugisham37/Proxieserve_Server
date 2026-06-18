"""Audit log HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session
from app.core.ratelimit import rate_limit
from app.modules.audit.schemas import AuditLogResponse
from app.modules.audit.service import AuditService
from app.modules.auth.dependencies import REQUIRE_ADMIN

router = APIRouter(prefix="/api/admin", tags=["admin-audit"])


def _get_service(session: AsyncSession = Depends(get_db_session)) -> AuditService:
    return AuditService(session)


@router.get(
    "/audit-log",
    response_model=ApiResponse[AuditLogResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-audit-log", 60, 60))],
)
async def list_audit_log(
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AuditService = Depends(_get_service),
) -> ApiResponse[AuditLogResponse]:
    data = await service.list_audit_log(kind=kind, limit=limit, offset=offset)
    return success_response(message="Audit log retrieved.", data=data)
