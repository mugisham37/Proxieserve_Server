"""Payment gateway abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.config import Settings, get_settings


@dataclass
class CardChargeResult:
    provider_transaction_id: str
    status: str
    session_token: str | None = None


@runtime_checkable
class PaymentGateway(Protocol):
    async def initiate_momo_push(
        self,
        *,
        phone_number: str,
        amount: int,
        currency: str,
        transaction_reference: str,
        operator: str,
    ) -> str: ...

    async def check_transaction_status(
        self,
        provider_transaction_id: str,
    ) -> tuple[str, dict[str, object] | None]: ...

    async def process_card_charge(
        self,
        *,
        card_token: str,
        amount: int,
        currency: str,
        transaction_reference: str,
    ) -> CardChargeResult: ...


class StubPaymentGateway:
    """Development gateway — simulates successful payments."""

    async def initiate_momo_push(
        self,
        *,
        phone_number: str,
        amount: int,
        currency: str,
        transaction_reference: str,
        operator: str,
    ) -> str:
        if phone_number.endswith("0000"):
            return f"stub-fail-{transaction_reference}"
        return f"stub-momo-{transaction_reference}"

    async def check_transaction_status(
        self,
        provider_transaction_id: str,
    ) -> tuple[str, dict[str, object] | None]:
        if "fail" in provider_transaction_id:
            return "failed", None
        return "paid", {"stub": True}

    async def process_card_charge(
        self,
        *,
        card_token: str,
        amount: int,
        currency: str,
        transaction_reference: str,
    ) -> CardChargeResult:
        if card_token.endswith("0000"):
            return CardChargeResult(
                provider_transaction_id=f"stub-card-fail-{transaction_reference}",
                status="failed",
                session_token=None,
            )
        return CardChargeResult(
            provider_transaction_id=f"stub-card-{transaction_reference}",
            status="approved",
            session_token=f"stub-3ds-{transaction_reference}",
        )


def get_payment_gateway(settings: Settings | None = None) -> PaymentGateway:
    resolved = settings or get_settings()
    gateway = getattr(resolved, "payment_gateway", "stub")
    if gateway == "stub":
        return StubPaymentGateway()
    return StubPaymentGateway()
