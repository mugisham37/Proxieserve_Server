"""Platform settings business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import write_audit_entry
from app.modules.platform.repository import PlatformRepository
from app.modules.platform.schemas import (
    AdminSettingsResponse,
    UpdateAdminSettingsRequest,
    months_to_retention_label,
    retention_label_to_months,
)


class PlatformService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PlatformRepository(session)

    async def get_settings(self) -> AdminSettingsResponse:
        row = await self.repo.get_or_create()
        await self.session.commit()
        return self._to_response(row)

    async def update_settings(
        self,
        *,
        admin_id: str,
        payload: UpdateAdminSettingsRequest,
        ip_address: str | None = None,
    ) -> AdminSettingsResponse:
        row = await self.repo.get_or_create()
        before = self._to_response(row)
        data = payload.model_dump(exclude_unset=True)
        if "acceptNewApps" in data:
            row.accept_new_apps = data["acceptNewApps"]
        if "guestApps" in data:
            row.guest_apps = data["guestApps"]
        if "dataRetention" in data and data["dataRetention"] is not None:
            row.data_retention_months = retention_label_to_months(data["dataRetention"])
        if "enforce2FA" in data:
            row.enforce_2fa = data["enforce2FA"]
        if "sessionTimeout" in data:
            row.session_timeout_minutes = data["sessionTimeout"]
        if "ipAllowlist" in data:
            row.ip_allowlist = data["ipAllowlist"]
        if "maintenanceMode" in data:
            row.maintenance_mode = data["maintenanceMode"]
            from app.core.middleware import invalidate_maintenance_mode_cache_async

            await invalidate_maintenance_mode_cache_async()
        row.updated_by = admin_id
        row.updated_at = datetime.now(UTC)
        after = self._to_response(row)
        await write_audit_entry(
            self.session,
            actor_id=admin_id,
            actor_role="staff:admin",
            action="settings.updated",
            resource_type="platform_settings",
            resource_id="global",
            details={"before": before.model_dump(), "after": after.model_dump()},
            ip_address=ip_address,
            kind="Config",
        )
        await self.session.commit()
        return after

    def _to_response(self, row) -> AdminSettingsResponse:
        return AdminSettingsResponse(
            acceptNewApps=row.accept_new_apps,
            guestApps=row.guest_apps,
            dataRetention=months_to_retention_label(row.data_retention_months),
            enforce2FA=row.enforce_2fa,
            sessionTimeout=row.session_timeout_minutes,
            ipAllowlist=row.ip_allowlist or "",
            maintenanceMode=row.maintenance_mode,
        )
