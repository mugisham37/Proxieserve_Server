"""Audit log write utility and read service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_id
from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditEntry, AuditLogResponse
from app.modules.auth.repository import AuthRepository


async def write_audit_entry(
    session: AsyncSession,
    *,
    actor_id: str | None,
    actor_role: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: dict[str, object],
    ip_address: str | None,
    kind: str,
) -> AuditLog:
    repo = AuditRepository(session)
    return await repo.insert_entry(
        id=generate_id("aud"),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        kind=kind,
    )


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuditRepository(session)
        self.auth_repo = AuthRepository(session)

    async def list_audit_log(
        self,
        *,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditLogResponse:
        rows, total, has_more = await self.repo.list_entries(
            kind_filter=kind,
            limit=limit,
            offset=offset,
        )
        entries: list[AuditEntry] = []
        for row in rows:
            actor_name = "System"
            actor_type = "system"
            if row.actor_id:
                user = await self.auth_repo.get_user_by_id(row.actor_id)
                if user:
                    actor_name = user.name
                if row.actor_role == "staff:admin":
                    actor_type = "admin"
                elif row.actor_role == "staff:agent":
                    actor_type = "agent"
            description = f"{row.action} on {row.resource_type}"
            if row.resource_id:
                description = f"{row.action}: {row.resource_id}"
            entries.append(
                AuditEntry(
                    id=row.id,
                    timestamp=row.created_at.isoformat(),
                    actor=actor_name,
                    actorType=actor_type,
                    description=description,
                    kind=row.kind,
                )
            )
        return AuditLogResponse(entries=entries, total=total, has_more=has_more)
