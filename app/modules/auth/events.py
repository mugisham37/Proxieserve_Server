"""Auth domain events."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.events import DomainEvent


@dataclass(slots=True)
class UserRegistered:
    user_id: str
    identifier: str

    def to_domain_event(self) -> DomainEvent:
        return DomainEvent(
            name="auth.user_registered",
            payload={"userId": self.user_id, "identifier": self.identifier},
        )


@dataclass(slots=True)
class ApplicationClaimRequested:
    user_id: str
    code: str
    phone: str

    def to_domain_event(self) -> DomainEvent:
        return DomainEvent(
            name="auth.application_claim_requested",
            payload={"userId": self.user_id, "code": self.code, "phone": self.phone},
        )
