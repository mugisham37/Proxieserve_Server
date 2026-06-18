"""HTTP routes for admin operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session, get_job_queue, get_redis
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.admin.schemas import (
    AgentListItem,
    AgentListResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    UpdateAgentRequest,
    UpdateAgentResponse,
)
from app.modules.admin.service import AdminService
from app.modules.auth.dependencies import REQUIRE_ADMIN, require_access_payload

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_admin_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> AdminService:
    return AdminService(session=session, redis=redis, settings=settings, job_queue=job_queue)


@router.post(
    "/agents",
    response_model=ApiResponse[CreateAgentResponse],
    status_code=201,
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-create-agent", 20, 60))],
)
async def create_agent(
    payload: CreateAgentRequest,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[CreateAgentResponse]:
    data = await service.create_agent(payload)
    return success_response(message="Agent account created.", data=data)


@router.get(
    "/agents",
    response_model=ApiResponse[AgentListResponse],
    dependencies=[REQUIRE_ADMIN],
)
async def list_agents(
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AgentListResponse]:
    data = await service.list_agents()
    return success_response(message="Agents retrieved.", data=data)


@router.get(
    "/agents/{agent_id}",
    response_model=ApiResponse[AgentListItem],
    dependencies=[REQUIRE_ADMIN],
)
async def get_agent(
    agent_id: str,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AgentListItem]:
    data = await service.get_agent(agent_id)
    return success_response(message="Agent retrieved.", data=data)


@router.patch(
    "/agents/{agent_id}",
    response_model=ApiResponse[UpdateAgentResponse],
    dependencies=[REQUIRE_ADMIN],
)
async def update_agent(
    agent_id: str,
    payload: UpdateAgentRequest,
    request: Request,
    token: dict[str, object] = Depends(require_access_payload),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[UpdateAgentResponse]:
    data = await service.update_agent(
        agent_id,
        payload,
        admin_id=str(token["user_id"]),
        ip_address=request.client.host if request.client else None,
    )
    return success_response(message="Agent updated.", data=data)
