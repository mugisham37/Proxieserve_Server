"""HTTP routes for application messages."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.dependencies import get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import (
    REQUIRE_ADMIN,
    REQUIRE_AGENT,
    REQUIRE_CLIENT,
    require_access_payload,
)
from app.modules.messages.schemas import CreateMessageRequest, MessageListResponse, MessageResponse
from app.modules.messages.service import MessagesService

client_router = APIRouter(prefix="/api/applications", tags=["messages"])
agent_router = APIRouter(prefix="/api/agent/cases", tags=["agent-messages"])
admin_router = APIRouter(prefix="/api/admin/applications", tags=["admin-messages"])


def _get_messages_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> MessagesService:
    return MessagesService(session=session, job_queue=job_queue)


@client_router.get(
    "/{code}/messages",
    response_model=ApiResponse[MessageListResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("client-list-messages", 60, 60))],
)
async def list_client_messages(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: MessagesService = Depends(_get_messages_service),
) -> ApiResponse[MessageListResponse]:
    data = await service.list_client_messages(code=code, client_id=str(token["user_id"]))
    return success_response(message="Messages retrieved.", data=data)


@client_router.post(
    "/{code}/messages",
    response_model=ApiResponse[MessageResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("client-post-message", 30, 60))],
)
async def post_client_message(
    code: str,
    payload: CreateMessageRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: MessagesService = Depends(_get_messages_service),
) -> ApiResponse[MessageResponse]:
    data = await service.post_client_message(
        code=code,
        client_id=str(token["user_id"]),
        payload=payload,
    )
    return success_response(message="Message sent.", data=data)


@client_router.patch(
    "/{code}/messages/read",
    response_model=ApiResponse[dict[str, int]],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("client-mark-read", 30, 60))],
)
async def mark_messages_read(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: MessagesService = Depends(_get_messages_service),
) -> ApiResponse[dict[str, int]]:
    count = await service.mark_read_by_client(code=code, client_id=str(token["user_id"]))
    return success_response(message="Messages marked as read.", data={"marked": count})


@agent_router.get(
    "/{code}/messages",
    response_model=ApiResponse[MessageListResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-list-messages", 60, 60))],
)
async def list_agent_messages(
    code: str,
    service: MessagesService = Depends(_get_messages_service),
) -> ApiResponse[MessageListResponse]:
    data = await service.list_staff_messages(code=code)
    return success_response(message="Messages retrieved.", data=data)


@agent_router.post(
    "/{code}/messages",
    response_model=ApiResponse[MessageResponse],
    dependencies=[REQUIRE_AGENT, Depends(rate_limit("agent-post-message", 30, 60))],
)
async def post_agent_message(
    code: str,
    payload: CreateMessageRequest,
    token: dict[str, object] = Depends(require_access_payload),
    service: MessagesService = Depends(_get_messages_service),
) -> ApiResponse[MessageResponse]:
    data = await service.post_agent_message(
        code=code,
        agent_id=str(token["user_id"]),
        payload=payload,
    )
    return success_response(message="Message sent.", data=data)


@admin_router.get(
    "/{code}/messages",
    response_model=ApiResponse[MessageListResponse],
    dependencies=[REQUIRE_ADMIN, Depends(rate_limit("admin-list-messages", 60, 60))],
)
async def list_admin_messages(
    code: str,
    service: MessagesService = Depends(_get_messages_service),
) -> ApiResponse[MessageListResponse]:
    data = await service.list_staff_messages(code=code)
    return success_response(message="Messages retrieved.", data=data)
