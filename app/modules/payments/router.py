"""Payment HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import ApiResponse, success_response
from app.core.config import get_settings
from app.core.dependencies import get_db_session, get_job_queue
from app.core.jobs import JobQueueManager
from app.core.payments import get_payment_gateway
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import REQUIRE_CLIENT, require_access_payload
from app.modules.payments.schemas import (
    CardWebhookRequest,
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    PaymentReceiptResponse,
    PaymentStatusResponse,
)
from app.modules.payments.service import PaymentsService

router = APIRouter(prefix="/api", tags=["payments"])


def _get_payments_service(
    session: AsyncSession = Depends(get_db_session),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> PaymentsService:
    return PaymentsService(
        session=session,
        gateway=get_payment_gateway(get_settings()),
        job_queue=job_queue,
    )


@router.post(
    "/payments/initiate",
    response_model=ApiResponse[InitiatePaymentResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("payment-initiate", 5, 60))],
)
async def initiate_payment(
    payload: InitiatePaymentRequest,
    request: Request,
    token: dict[str, object] = Depends(require_access_payload),
    service: PaymentsService = Depends(_get_payments_service),
) -> ApiResponse[InitiatePaymentResponse]:
    phone_or_card = payload.phone_number or payload.card_token
    data = await service.initiate_payment(
        application_code=payload.application_code,
        method=payload.method,
        phone_or_card=phone_or_card,
        operator=payload.operator,
        client_id=str(token["user_id"]),
        ip_address=request.client.host if request.client else None,
    )
    return success_response(message="Payment initiated.", data=data)


@router.get(
    "/payments/{transaction_id}/status",
    response_model=ApiResponse[PaymentStatusResponse],
    dependencies=[REQUIRE_CLIENT, Depends(rate_limit("payment-status", 60, 60))],
)
async def get_payment_status(
    transaction_id: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: PaymentsService = Depends(_get_payments_service),
) -> ApiResponse[PaymentStatusResponse]:
    data = await service.get_payment_status(
        transaction_id=transaction_id,
        client_id=str(token["user_id"]),
    )
    return success_response(message="Payment status retrieved.", data=data)


@router.post(
    "/payments/card/webhook",
    response_model=ApiResponse[dict[str, bool]],
)
async def card_webhook(
    payload: CardWebhookRequest,
    request: Request,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    service: PaymentsService = Depends(_get_payments_service),
) -> ApiResponse[dict[str, bool]]:
    settings = get_settings()
    secret = getattr(settings, "payment_webhook_secret", "dev-webhook-secret")
    if x_webhook_secret != secret:
        from app.core.exceptions import UnauthorizedError

        raise UnauthorizedError(message="Invalid webhook secret.")
    await service.handle_card_webhook(
        provider_transaction_id=payload.provider_transaction_id,
        status=payload.status,
        ip_address=request.client.host if request.client else None,
    )
    return success_response(message="Webhook processed.", data={"ok": True})


@router.get(
    "/applications/{code}/payment/receipt",
    response_model=ApiResponse[PaymentReceiptResponse],
    dependencies=[REQUIRE_CLIENT],
)
async def get_payment_receipt(
    code: str,
    token: dict[str, object] = Depends(require_access_payload),
    service: PaymentsService = Depends(_get_payments_service),
) -> ApiResponse[PaymentReceiptResponse]:
    data = await service.get_receipt(
        application_code=code,
        client_id=str(token["user_id"]),
    )
    return success_response(message="Receipt retrieved.", data=data)
