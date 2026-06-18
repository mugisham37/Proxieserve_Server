"""Business logic for admin operations."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AgentNotFoundError, EmailAlreadyInUseError
from app.core.jobs import JobQueueManager
from app.core.security import async_hash_password, generate_id
from app.modules.admin.schemas import (
    AgentListItem,
    AgentListResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    UpdateAgentRequest,
    UpdateAgentResponse,
)
from app.modules.audit.service import write_audit_entry
from app.modules.auth.models import StaffProfile, User


class AdminService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        settings: Settings,
        job_queue: JobQueueManager,
    ) -> None:
        self.session = session
        self.redis = redis
        self.settings = settings
        self.job_queue = job_queue

    async def create_agent(self, request: CreateAgentRequest) -> CreateAgentResponse:
        email = str(request.email).lower()
        existing = await self.session.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise EmailAlreadyInUseError()

        temp_password = request.temporary_password or secrets.token_urlsafe(12)
        user_id = generate_id("usr")
        now = datetime.now(UTC)
        user = User(
            user_id=user_id,
            name=request.name,
            email=email,
            phone_e164=None,
            password_hash=await async_hash_password(temp_password),
            role="staff:agent",
            is_active=True,
            is_email_verified=True,
            language="en",
            created_at=now,
            updated_at=now,
        )
        self.session.add(user)
        await self.session.flush()

        profile = StaffProfile(
            user_id=user_id,
            totp_secret_encrypted=None,
            twofa_enabled=True,
            sms_phone_e164=None,
            created_at=now,
        )
        self.session.add(profile)

        invite_sent = False
        try:
            await self.job_queue.enqueue(
                "send_email_job",
                to=email,
                subject="Your ProxiServe agent account",
                body=(
                    f"<p>Hello {request.name},</p>"
                    f"<p>Your ProxiServe agent account has been created.</p>"
                    f"<p><strong>Email:</strong> {email}<br>"
                    f"<strong>Temporary password:</strong> {temp_password}</p>"
                    f"<p>Please log in at /staff/login and change your password immediately.</p>"
                ),
            )
            invite_sent = True
        except Exception:
            pass

        await self.session.commit()
        return CreateAgentResponse(
            agent_id=user_id,
            name=request.name,
            email=email,
            created_at=now.isoformat(),
            invite_sent=invite_sent,
        )

    async def list_agents(self) -> AgentListResponse:
        result = await self.session.execute(
            select(User, StaffProfile)
            .join(StaffProfile, StaffProfile.user_id == User.user_id)
            .where(User.role == "staff:agent")
            .order_by(User.created_at.desc())
        )
        rows = result.all()
        agents = [
            AgentListItem(
                agent_id=user.user_id,
                name=user.name,
                email=user.email or "",
                is_active=user.is_active,
                twofa_enabled=profile.twofa_enabled,
                created_at=user.created_at.isoformat(),
            )
            for user, profile in rows
        ]
        return AgentListResponse(agents=agents)

    async def get_agent(self, agent_id: str) -> AgentListItem:
        result = await self.session.execute(
            select(User, StaffProfile)
            .join(StaffProfile, StaffProfile.user_id == User.user_id)
            .where(User.user_id == agent_id, User.role == "staff:agent")
        )
        row = result.first()
        if row is None:
            raise AgentNotFoundError()
        user, profile = row
        return AgentListItem(
            agent_id=user.user_id,
            name=user.name,
            email=user.email or "",
            is_active=user.is_active,
            twofa_enabled=profile.twofa_enabled,
            created_at=user.created_at.isoformat(),
        )

    async def update_agent(
        self,
        agent_id: str,
        request: UpdateAgentRequest,
        *,
        admin_id: str | None = None,
        ip_address: str | None = None,
    ) -> UpdateAgentResponse:
        result = await self.session.execute(
            select(User, StaffProfile)
            .join(StaffProfile, StaffProfile.user_id == User.user_id)
            .where(User.user_id == agent_id, User.role == "staff:agent")
        )
        row = result.first()
        if row is None:
            raise AgentNotFoundError()
        user, profile = row

        updated: list[str] = []

        if request.is_active is not None:
            user.is_active = request.is_active
            updated.append("is_active")

        if request.reset_password:
            temp_password = secrets.token_urlsafe(12)
            user.password_hash = await async_hash_password(temp_password)
            updated.append("password")
            try:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=user.email,
                    subject="Your ProxiServe password has been reset",
                    body=(
                        f"<p>Hello {user.name},</p>"
                        f"<p>Your password has been reset by an administrator.</p>"
                        f"<p><strong>Temporary password:</strong> {temp_password}</p>"
                        f"<p>Please log in and change your password immediately.</p>"
                    ),
                )
            except Exception:
                pass

        if request.force_2fa_reset:
            profile.totp_secret_encrypted = None
            profile.twofa_enabled = True
            updated.append("2fa_reset")

        if updated and admin_id:
            await write_audit_entry(
                self.session,
                actor_id=admin_id,
                actor_role="staff:admin",
                action="agent.updated",
                resource_type="agent",
                resource_id=agent_id,
                details={"updated": updated},
                ip_address=ip_address,
                kind="Privileged",
            )

        await self.session.commit()
        return UpdateAgentResponse(agent_id=agent_id, updated=updated)
