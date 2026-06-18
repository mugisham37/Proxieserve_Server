"""Broadcast HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import REQUIRE_ADMIN, require_access_payload
from app.modules.broadcasts.schemas import (
    BroadcastListResponse,
    BroadcastRecordResponse,
    CreateBroadcastRequest,
)
from app.modules.broadcasts.service import BroadcastsService

router = APIRouter(prefix="/api/admin", tags=["admin-broadcasts"])


def _get_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> BroadcastsService:
    return BroadcastsService(session=session, job_queue=job_queue)


@router.get(
    "/broadcasts",
    response_model=ApiResponse[BroadcastListResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-list-broadcasts", 30, 60))],
)
async def list_broadcasts(
    service: BroadcastsService = Depends(_get_service),
) -> ApiResponse[BroadcastListResponse]:
    data = await service.list_broadcasts()
    return success_response(message="Broadcasts retrieved.", data=data)


@router.post(
    "/broadcasts",
    response_model=ApiResponse[BroadcastRecordResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-create-broadcast", 10, 60))],
)
async def create_broadcast(
    payload: CreateBroadcastRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: BroadcastsService = Depends(_get_service),
) -> ApiResponse[BroadcastRecordResponse]:
    data = await service.create_broadcast(admin_id=str(token["user_id"]), payload=payload)
    return success_response(message="Broadcast created.", data=data)
