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
