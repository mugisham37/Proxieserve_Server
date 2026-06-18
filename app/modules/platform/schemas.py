"""Platform settings DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdminSettingsResponse(BaseModel):
    acceptNewApps: bool
    guestApps: bool
    dataRetention: str
    compactTables: bool = False
    enforce2FA: bool
    sessionTimeout: int
    ipAllowlist: str
    maintenanceMode: bool


class UpdateAdminSettingsRequest(BaseModel):
    acceptNewApps: bool | None = None
    guestApps: bool | None = None
    dataRetention: str | None = None
    enforce2FA: bool | None = None
    sessionTimeout: int | None = Field(default=None, ge=15, le=480)
    ipAllowlist: str | None = None
    maintenanceMode: bool | None = None


def months_to_retention_label(months: int) -> str:
    if months >= 999:
        return "forever"
    return f"{months}-months"


def retention_label_to_months(label: str) -> int:
    if label == "forever":
        return 999
    if label.endswith("-months"):
        return int(label.replace("-months", ""))
    return 24
