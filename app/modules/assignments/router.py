"""HTTP routes for assignments and agent settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.assignments.schemas import (
    AgentMetricsResponse,
    AgentSettingsResponse,
    AgentSkillsResponse,
    LeaderboardResponse,
    SetAgentSkillsRequest,
    UpdateAgentSettingsRequest,
)
from app.modules.assignments.service import AssignmentsService
from app.modules.auth.dependencies import REQUIRE_ADMIN, REQUIRE_AGENT, require_access_payload

router = APIRouter(tags=["assignments"])
agent_router = APIRouter(prefix="/api/agent", tags=["agent-settings"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin-assignments"])


def _get_assignments_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> AssignmentsService:
    return AssignmentsService(session=session, job_queue=job_queue)


@agent_router.get(
    "/settings",
    response_model=ApiResponse[AgentSettingsResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-get-settings", 30, 60))],
)
async def get_agent_settings(
    token: dict[str, object] = Depends(require_access_payload),
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[AgentSettingsResponse]:
    data = await service.get_agent_settings(str(token["user_id"]))
    return success_response(message="Settings retrieved.", data=data)


@agent_router.put(
    "/settings",
    response_model=ApiResponse[AgentSettingsResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-update-settings", 20, 60))],
)
async def update_agent_settings(
    payload: UpdateAgentSettingsRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[AgentSettingsResponse]:
    data = await service.update_agent_settings(str(token["user_id"]), payload)
    return success_response(message="Settings updated.", data=data)


@agent_router.get(
    "/skills",
    response_model=ApiResponse[AgentSkillsResponse],
    dependencies=[REQUIRE_AGENT],
)
async def get_own_skills(
    token: dict[str, object] = Depends(require_access_payload),
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[AgentSkillsResponse]:
    data = await service.get_agent_skills(str(token["user_id"]))
    return success_response(message="Skills retrieved.", data=data)


@agent_router.get(
    "/metrics",
    response_model=ApiResponse[AgentMetricsResponse],
    dependencies=[REQUIRE_AGENT],
)
async def get_agent_metrics(
    token: dict[str, object] = Depends(require_access_payload),
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[AgentMetricsResponse]:
    data = await service.get_agent_metrics(str(token["user_id"]))
    return success_response(message="Metrics retrieved.", data=data)


@admin_router.get(
    "/agents/{agent_id}/skills",
    response_model=ApiResponse[AgentSkillsResponse],
    dependencies=[REQUIRE_ADMIN],
)
async def get_agent_skills_admin(
    agent_id: str,
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[AgentSkillsResponse]:
    data = await service.get_agent_skills(agent_id)
    return success_response(message="Skills retrieved.", data=data)


@admin_router.patch(
    "/agents/{agent_id}/skills",
    response_model=ApiResponse[AgentSkillsResponse],
    dependencies=[REQUIRE_ADMIN],
)
async def set_agent_skills(
    agent_id: str,
    payload: SetAgentSkillsRequest,
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[AgentSkillsResponse]:
    data = await service.set_agent_skills(agent_id=agent_id, payload=payload)
    return success_response(message="Skills updated.", data=data)


@admin_router.get(
    "/agents/leaderboard",
    response_model=ApiResponse[LeaderboardResponse],
    dependencies=[REQUIRE_ADMIN],
)
async def get_leaderboard(
    service: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[LeaderboardResponse]:
    data = await service.get_admin_leaderboard()
    return success_response(message="Leaderboard retrieved.", data=data)
