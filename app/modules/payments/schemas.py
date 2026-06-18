"""Payment DTOs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class InitiatePaymentRequest(BaseModel):
    application_code: str
    method: str
    phone_number: str | None = None
    card_token: str | None = None
    operator: str | None = None


class InitiatePaymentResponse(BaseModel):
    paymentId: str
    transactionId: str
    status: str
    expiresAt: datetime | None = None
    sessionToken: str | None = None


class PaymentStatusResponse(BaseModel):
    transactionId: str
    status: str
    paidAt: datetime | None = None


class PaymentReceiptResponse(BaseModel):
    serviceName: str
    trackingCode: str
    amount: int
    governmentFee: int
    vatAmount: int
    method: str
    transactionId: str
    receiptNumber: str
    paidAt: datetime
    applicationCode: str


class PaymentInfoResponse(BaseModel):
    method: str
    amount: int
    governmentFee: int
    vatRate: float
    paidAt: datetime | None = None
    receiptNumber: str | None = None


class CardWebhookRequest(BaseModel):
    provider_transaction_id: str
    status: str = "paid"
