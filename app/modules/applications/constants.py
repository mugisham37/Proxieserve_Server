"""Application lifecycle constants."""

from __future__ import annotations

APPLICATION_STATUSES = frozenset({
    "received",
    "under_review",
    "in_progress",
    "awaiting_client",
    "submitted_to_authority",
    "awaiting_response",
    "completed",
    "rejected",
    "cancelled",
})

PAYMENT_STATUSES = frozenset({"pending", "paid", "failed", "waived"})

VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "received": {"under_review", "cancelled"},
    "under_review": {"in_progress", "awaiting_client", "rejected"},
    "in_progress": {"submitted_to_authority", "awaiting_client", "rejected"},
    "awaiting_client": {"in_progress", "rejected", "cancelled"},
    "submitted_to_authority": {"awaiting_response", "completed", "rejected"},
    "awaiting_response": {"completed", "rejected", "in_progress"},
    "completed": set(),
    "rejected": set(),
    "cancelled": set(),
}

CLIENT_CANCELLABLE = frozenset({"received", "awaiting_client"})

SYSTEM_MESSAGES: dict[str, str] = {
    "under_review": "Your application has been assigned to an agent and is now under review.",
    "in_progress": "Your agent has started actively processing your application.",
    "awaiting_client": "Your agent needs additional information from you. Please check your messages for details.",
    "submitted_to_authority": "Your application has been submitted to the relevant authority.",
    "awaiting_response": "We are awaiting a response from the authority.",
    "completed": "Congratulations — your application has been successfully completed.",
    "rejected": "Your application has been rejected. Please check your messages for details.",
    "cancelled": "Your application has been cancelled.",
}

TERMINAL_STATUSES = frozenset({"completed", "rejected", "cancelled"})

ACTIVE_STATUSES = frozenset({
    "received",
    "under_review",
    "in_progress",
    "submitted_to_authority",
    "awaiting_response",
    "awaiting_client",
})

STATUS_DISPLAY_MAP: dict[str, str] = {
    "received": "in-progress",
    "under_review": "in-progress",
    "in_progress": "in-progress",
    "submitted_to_authority": "in-progress",
    "awaiting_response": "on-hold",
    "awaiting_client": "action-required",
    "completed": "completed",
    "rejected": "discontinued",
    "cancelled": "discontinued",
}

SERVICE_CATEGORIES = frozenset({"identity", "business", "tax", "welfare", "permits", "other"})


def compute_sla_deadline(submitted_at, eta_business_days: int):
    """Compute SLA deadline from tier ETA (business days × 1.4, rounded up)."""
    from datetime import timedelta
    import math

    calendar_days = math.ceil(eta_business_days * 1.4)
    return submitted_at + timedelta(days=calendar_days)


def compute_sla_state(app, *, now=None) -> str:
    """Return sla_state: ok, warn, or over based on sla_deadline."""
    from datetime import UTC, datetime, timedelta

    if now is None:
        now = datetime.now(UTC)
    if app.status in TERMINAL_STATUSES:
        return "ok"
    if app.sla_deadline is None:
        return "ok"
    if now > app.sla_deadline:
        return "over"
    if now >= app.sla_deadline - timedelta(hours=24):
        return "warn"
    return "ok"


def status_display(internal_status: str) -> str:
    return STATUS_DISPLAY_MAP.get(internal_status, "in-progress")
