"""HTTP routes for applications."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.applications.schemas import (
    AdminApplicationListResponse,
    AgentCaseListResponse,
    ApplicationClaimData,
    ApplicationClaimRequest,
    ApplicationDetailResponse,
    ApplicationListResponse,
    ApplicationLookupData,
    CancelApplicationRequest,
    DashboardSummaryResponse,
    SubmitApplicationRequest,
    SubmitApplicationResponse,
    TrackerResponse,
    UpdateStatusRequest,
)
from app.modules.analytics.schemas import AnalyticsResponse
from app.modules.analytics.service import AnalyticsService
from app.modules.applications.service import ApplicationsService
from app.modules.assignments.schemas import AssignAgentRequest
from app.modules.assignments.service import AssignmentsService
from app.modules.auth.dependencies import (
    REQUIRE_ADMIN,
    REQUIRE_AGENT,
    REQUIRE_CLIENT,
    require_access_payload,
)

client_router = APIRouter(prefix="/api/applications", tags=["applications"])
agent_router = APIRouter(prefix="/api/agent/cases", tags=["agent-cases"])
admin_router = APIRouter(prefix="/api/admin/applications", tags=["admin-applications"])
tracker_router = APIRouter(prefix="/api/track", tags=["tracker"])
legacy_router = APIRouter(prefix="/api/applications", tags=["applications-legacy"])


def _get_applications_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> ApplicationsService:
    return ApplicationsService(session=session, job_queue=job_queue)


def _get_assignments_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> AssignmentsService:
    return AssignmentsService(session=session, job_queue=job_queue)


@client_router.post(
    "/submit",
    response_model=ApiResponse[SubmitApplicationResponse],
    status_code=201,
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("applications-submit", 5, 600))],
)
async def submit_application(
    payload: SubmitApplicationRequest,
    request: Request,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[SubmitApplicationResponse]:
    data = await service.submit_application(
        client_id=str(token["user_id"]),
        payload=payload,
        submission_ip=request.client.host if request.client else None,
    )
    return success_response(message="Application submitted.", data=data)


@client_router.get(
    "",
    response_model=ApiResponse[ApplicationListResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("applications-list", 60, 60))],
)
async def list_applications(
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationListResponse]:
    data = await service.list_client_applications(str(token["user_id"]))
    return success_response(message="Applications retrieved.", data=data)


@client_router.get(
    "/summary",
    response_model=ApiResponse[DashboardSummaryResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("applications-summary", 60, 60))],
)
async def get_applications_summary(
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[DashboardSummaryResponse]:
    data = await service.get_dashboard_summary(str(token["user_id"]))
    return success_response(message="Dashboard summary retrieved.", data=data)


@client_router.get(
    "/{code}",
    response_model=ApiResponse[ApplicationDetailResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("applications-detail", 60, 60))],
)
async def get_application(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationDetailResponse]:
    data = await service.get_client_application(code=code, client_id=str(token["user_id"]))
    return success_response(message="Application retrieved.", data=data)


@client_router.post(
    "/{code}/cancel",
    response_model=ApiResponse[None],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("applications-cancel", 10, 60))],
)
async def cancel_application(
    code: str,
    payload: CancelApplicationRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[None]:
    await service.cancel_application(
        code=code,
        client_id=str(token["user_id"]),
        payload=payload,
    )
    return success_response(message="Application cancelled.", data=None)


@legacy_router.get(
    "/lookup",
    response_model=ApiResponse[ApplicationLookupData],
    dependencies=[Depends(rate_limit("applications-lookup", 20, 60))],
)
async def lookup_application(
    code: str,
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationLookupData]:
    result = await service.lookup_by_code(code)
    return success_response(message="Application found.", data=result)


@legacy_router.post(
    "/claim",
    response_model=ApiResponse[ApplicationClaimData],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("applications-claim", 10, 60))],
)
async def claim_application(
    payload: ApplicationClaimRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationClaimData]:
    await service.claim(
        code=payload.code,
        phone=payload.phone,
        client_id=str(token["user_id"]),
    )
    return success_response(message="Application claim accepted.", data=ApplicationClaimData())


@tracker_router.get(
    "/{code}",
    response_model=ApiResponse[TrackerResponse],
    dependencies=[Depends(rate_limit("track-application", 30, 60))],
)
async def track_application(
    code: str,
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[TrackerResponse]:
    data = await service.get_tracker(code)
    return success_response(message="Application status retrieved.", data=data)


@agent_router.get(
    "",
    response_model=ApiResponse[AgentCaseListResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-cases-list", 60, 60))],
)
async def list_agent_cases(
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[AgentCaseListResponse]:
    data = await service.list_agent_cases(str(token["user_id"]))
    return success_response(message="Cases retrieved.", data=data)


@agent_router.get(
    "/unassigned",
    response_model=ApiResponse,
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-unassigned", 60, 60))],
)
async def list_unassigned_cases(
    assignments: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse:
    data = await assignments.list_unassigned_queue()
    return success_response(message="Unassigned queue retrieved.", data=data)


@agent_router.post(
    "/unassigned/{code}/claim",
    response_model=ApiResponse[None],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-claim-case", 20, 60))],
)
async def claim_unassigned_case(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    assignments: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[None]:
    await assignments.claim_unassigned(code=code, agent_id=str(token["user_id"]))
    return success_response(message="Case claimed.", data=None)


@agent_router.get(
    "/{code}",
    response_model=ApiResponse[ApplicationDetailResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-case-detail", 60, 60))],
)
async def get_agent_case(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationDetailResponse]:
    data = await service.get_agent_case(code=code, agent_id=str(token["user_id"]))
    return success_response(message="Case retrieved.", data=data)


@agent_router.patch(
    "/{code}/status",
    response_model=ApiResponse[ApplicationDetailResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-update-status", 30, 60))],
)
async def update_agent_case_status(
    code: str,
    payload: UpdateStatusRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationDetailResponse]:
    data = await service.transition_status(
        code=code,
        payload=payload,
        user_id=str(token["user_id"]),
        user_role=str(token["role"]),
        force=False,
    )
    return success_response(message="Status updated.", data=data)


@admin_router.get(
    "",
    response_model=ApiResponse[AdminApplicationListResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-applications-list", 60, 60))],
)
async def list_admin_applications(
    status: str | None = None,
    service_id: str | None = None,
    agent_id: str | None = None,
    tier: str | None = None,
    payment_status: str | None = None,
    offset: int = 0,
    limit: int = 50,
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[AdminApplicationListResponse]:
    data = await service.list_admin_applications(
        status=status,
        service_id=service_id,
        agent_id=agent_id,
        tier=tier,
        payment_status=payment_status,
        offset=offset,
        limit=limit,
    )
    return success_response(message="Applications retrieved.", data=data)


@admin_router.get(
    "/{code}",
    response_model=ApiResponse[ApplicationDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-application-detail", 60, 60))],
)
async def get_admin_application(
    code: str,
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationDetailResponse]:
    data = await service.get_admin_application(code)
    return success_response(message="Application retrieved.", data=data)


@admin_router.patch(
    "/{code}/assign",
    response_model=ApiResponse[None],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-assign-agent", 30, 60))],
)
async def assign_application(
    code: str,
    payload: AssignAgentRequest,
    request: Request,
    token: dict[str, object] = Depends(require_access_payload),
    assignments: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[None]:
    await assignments.assign_by_admin(
        code=code,
        admin_id=str(token["user_id"]),
        payload=payload,
        ip_address=request.client.host if request.client else None,
    )
    return success_response(message="Application assigned.", data=None)


@admin_router.post(
    "/{code}/auto-assign",
    response_model=ApiResponse[dict[str, bool]],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-auto-assign", 30, 60))],
)
async def auto_assign_application(
    code: str,
    assignments: AssignmentsService = Depends(_get_assignments_service),
) -> ApiResponse[dict[str, bool]]:
    assigned = await assignments.auto_assign_by_admin(code=code)
    return success_response(
        message="Auto-assignment completed." if assigned else "No agent qualified.",
        data={"assigned": assigned},
    )


@admin_router.patch(
    "/{code}/status",
    response_model=ApiResponse[ApplicationDetailResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-update-status", 30, 60))],
)
async def admin_update_status(
    code: str,
    payload: UpdateStatusRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: ApplicationsService = Depends(_get_applications_service),
) -> ApiResponse[ApplicationDetailResponse]:
    data = await service.transition_status(
        code=code,
        payload=payload,
        user_id=str(token["user_id"]),
        user_role=str(token["role"]),
        force=True,
    )
    return success_response(message="Status updated.", data=data)


analytics_router = APIRouter(prefix="/api/admin", tags=["admin-analytics"])


def _get_analytics_service(
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsService:
    return AnalyticsService(session)


@analytics_router.get(
    "/analytics",
    response_model=ApiResponse[AnalyticsResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-analytics", 30, 60))],
)
async def get_analytics(
    service: AnalyticsService = Depends(_get_analytics_service),
) -> ApiResponse[AnalyticsResponse]:
    data = await service.get_analytics()
    return success_response(message="Analytics retrieved.", data=data)
