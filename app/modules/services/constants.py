"""Service template constants."""

from __future__ import annotations

SERVICE_CATEGORIES = frozenset({"identity", "business", "tax", "welfare", "permits", "other"})
SERVICE_STATUSES = frozenset({"draft", "active", "paused", "unavailable", "archived"})
DOC_TYPES = frozenset({"id", "certificate", "photo", "form", "proof", "other"})
FIELD_TYPES = frozenset({"text", "textarea", "select", "radio_card", "date", "switch", "checkbox"})
PRICING_TIERS = frozenset({"standard", "express", "urgent"})

COLOUR_HEX_MAP = {
    "marigold": "#F5A623",
    "pink": "#E91E8C",
    "green": "#2ECC71",
    "blue": "#3498DB",
    "red": "#E74C3C",
    "cream": "#F5F0E8",
}

VALID_SERVICE_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "archived"},
    "active": {"paused", "unavailable", "archived"},
    "paused": {"active", "archived"},
    "unavailable": {"active", "archived"},
    "archived": set(),
}
