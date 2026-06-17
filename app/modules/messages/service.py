"""Business logic for application messages."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationAccessForbiddenError, ApplicationNotFoundError
from app.core.jobs import JobQueueManager
from app.core.security import generate_id
from app.modules.applications.repository import ApplicationsRepository
from app.modules.auth.repository import AuthRepository
from app.modules.messages.repository import MessagesRepository
from app.modules.messages.schemas import CreateMessageRequest, MessageListResponse, MessageResponse


class MessagesService:
    def __init__(
        self,
        session: AsyncSession,
        job_queue: JobQueueManager | None = None,
    ) -> None:
        self.session = session
        self.repo = MessagesRepository(session)
        self.apps_repo = ApplicationsRepository(session)
        self.auth_repo = AuthRepository(session)
        self.job_queue = job_queue

    async def create_system_message(
        self,
        *,
        application_id: str,
        content: str,
    ) -> MessageResponse:
        message = await self.repo.create_message(
            message_id=generate_id("msg"),
            application_id=application_id,
            sender_id=None,
            sender_role="system",
            content=content,
            is_internal=False,
            is_system=True,
            attachments=[],
            is_read_by_client=False,
        )
        return MessageResponse.model_validate(message)

    async def list_client_messages(
        self,
        *,
        code: str,
        client_id: str,
    ) -> MessageListResponse:
        app = await self._get_owned_app(code, client_id)
        messages = await self.repo.list_for_client(app.application_id)
        return MessageListResponse(
            messages=[MessageResponse.model_validate(m) for m in messages]
        )

    async def list_staff_messages(self, *, code: str) -> MessageListResponse:
        app = await self._get_app_or_raise(code)
        messages = await self.repo.list_for_staff(app.application_id)
        return MessageListResponse(
            messages=[MessageResponse.model_validate(m) for m in messages]
        )

    async def post_client_message(
        self,
        *,
        code: str,
        client_id: str,
        payload: CreateMessageRequest,
    ) -> MessageResponse:
        app = await self._get_owned_app(code, client_id)
        message = await self.repo.create_message(
            message_id=generate_id("msg"),
            application_id=app.application_id,
            sender_id=client_id,
            sender_role="client",
            content=payload.content,
            is_internal=False,
            is_system=False,
            attachments=payload.attachments,
            is_read_by_client=True,
        )
        await self.session.commit()
        if app.assigned_agent_id and self.job_queue:
            agent = await self.auth_repo.get_user_by_id(app.assigned_agent_id)
            if agent and agent.email:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=agent.email,
                    subject=f"Client replied — {app.code}",
                    body=f"A client has sent a new message on case {app.code}:\n\n{payload.content[:200]}",
                )
        return MessageResponse.model_validate(message)

    async def post_agent_message(
        self,
        *,
        code: str,
        agent_id: str,
        payload: CreateMessageRequest,
    ) -> MessageResponse:
        app = await self._get_assigned_app(code, agent_id)
        message = await self.repo.create_message(
            message_id=generate_id("msg"),
            application_id=app.application_id,
            sender_id=agent_id,
            sender_role="staff:agent",
            content=payload.content,
            is_internal=payload.is_internal,
            is_system=False,
            attachments=payload.attachments,
            is_read_by_client=False,
        )
        await self.session.commit()
        if not payload.is_internal and self.job_queue:
            client = await self.auth_repo.get_user_by_id(app.client_id)
            if client and client.email:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=client.email,
                    subject=f"New message from your agent — {app.code}",
                    body=f"Your agent sent a message on {app.code}:\n\n{payload.content[:200]}",
                )
        return MessageResponse.model_validate(message)

    async def mark_read_by_client(self, *, code: str, client_id: str) -> int:
        app = await self._get_owned_app(code, client_id)
        count = await self.repo.mark_read_by_client(app.application_id)
        await self.session.commit()
        return count

    async def _get_app_or_raise(self, code: str):
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        return app

    async def _get_owned_app(self, code: str, client_id: str):
        app = await self._get_app_or_raise(code)
        if app.client_id != client_id:
            raise ApplicationAccessForbiddenError(code=code)
        return app

    async def _get_assigned_app(self, code: str, agent_id: str):
        app = await self._get_app_or_raise(code)
        if app.assigned_agent_id != agent_id:
            raise ApplicationAccessForbiddenError(code=code)
        return app
