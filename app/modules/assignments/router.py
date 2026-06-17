"""HTTP routes for assignments and agent settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.assignments.schemas import AgentSettingsResponse, UpdateAgentSettingsRequest
from app.modules.assignments.service import AssignmentsService
from app.modules.auth.dependencies import REQUIRE_AGENT, require_access_payload

router = APIRouter(prefix="/api/agent", tags=["agent-settings"])


def _get_assignments_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> AssignmentsService:
    return AssignmentsService(session=session, job_queue=job_queue)


@router.get(
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


@router.put(
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
