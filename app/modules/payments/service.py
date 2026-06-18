"""Payment business logic."""

from __future__ import annotations

import random
import string
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ApplicationAccessForbiddenError,
    ApplicationNotFoundError,
    PaymentAlreadyPaidError,
    PaymentExpiredError,
    PaymentGatewayError,
    PaymentNotFoundError,
)
from app.core.jobs import JobQueueManager
from app.core.payments import PaymentGateway
from app.core.security import generate_id
from app.modules.applications.repository import ApplicationsRepository
from app.modules.audit.service import write_audit_entry
from app.modules.auth.repository import AuthRepository
from app.modules.messages.service import MessagesService
from app.modules.payments.repository import PaymentsRepository
from app.modules.payments.schemas import (
    InitiatePaymentResponse,
    PaymentReceiptResponse,
    PaymentStatusResponse,
)
from app.modules.services.repository import ServicesRepository

METHOD_LABELS = {
    "mtn-momo": "MTN Mobile Money",
    "airtel-money": "Airtel Money",
    "card": "Card",
    "agent": "Agent Cash",
}

VAT_RATE = Decimal("0.18")


class PaymentsService:
    def __init__(
        self,
        session: AsyncSession,
        gateway: PaymentGateway,
        job_queue: JobQueueManager | None = None,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self.job_queue = job_queue
        self.repo = PaymentsRepository(session)
        self.apps_repo = ApplicationsRepository(session)
        self.services_repo = ServicesRepository(session)
        self.auth_repo = AuthRepository(session)
        self.messages_service = MessagesService(session, job_queue)

    async def initiate_payment(
        self,
        *,
        application_code: str,
        method: str,
        phone_or_card: str | None,
        operator: str | None,
        client_id: str,
        ip_address: str | None = None,
    ) -> InitiatePaymentResponse:
        app = await self.apps_repo.get_by_code(application_code)
        if app is None or app.client_id != client_id:
            raise ApplicationNotFoundError() if app is None else ApplicationAccessForbiddenError(code=application_code)
        if app.payment_status == "paid":
            raise PaymentAlreadyPaidError()
        service = await self.services_repo.get_by_id(app.service_id, load_nested=True)
        tier = next((t for t in (service.pricing_tiers if service else []) if t.tier == app.tier), None)
        if tier is None:
            raise ApplicationNotFoundError()
        service_fee = tier.platform_fee
        government_fee = tier.government_fee
        amount_rwf = service_fee + 0
        payment_id = generate_id("pay")
        now = datetime.now(UTC)
        if method in {"mtn-momo", "airtel-money"}:
            if not phone_or_card:
                raise PaymentGatewayError(message="Phone number is required for mobile money.")
            provider_id = await self.gateway.initiate_momo_push(
                phone_number=phone_or_card,
                amount=amount_rwf,
                currency="RWF",
                transaction_reference=payment_id,
                operator=operator or method,
            )
            expires_at = now + timedelta(seconds=120)
            payment = await self.repo.create(
                payment_id=payment_id,
                application_id=app.application_id,
                amount_rwf=amount_rwf,
                government_fee_rwf=government_fee,
                platform_fee_rwf=0,
                vat_rate=VAT_RATE,
                method=method,
                provider_transaction_id=provider_id,
                status="processing",
                masked_phone=phone_or_card[-4:] if len(phone_or_card) >= 4 else phone_or_card,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            await self.session.commit()
            if self.job_queue:
                await self.job_queue.enqueue(
                    "payment_timeout_job",
                    payment_id=payment.payment_id,
                    _defer_by=120,
                )
            return InitiatePaymentResponse(
                paymentId=payment.payment_id,
                transactionId=payment.payment_id,
                status="processing",
                expiresAt=expires_at,
            )
        if method == "card":
            if not phone_or_card:
                raise PaymentGatewayError(message="Card token is required.")
            result = await self.gateway.process_card_charge(
                card_token=phone_or_card,
                amount=amount_rwf,
                currency="RWF",
                transaction_reference=payment_id,
            )
            brand = "visa" if phone_or_card.startswith("4") else "mastercard"
            payment = await self.repo.create(
                payment_id=payment_id,
                application_id=app.application_id,
                amount_rwf=amount_rwf,
                government_fee_rwf=government_fee,
                platform_fee_rwf=0,
                vat_rate=VAT_RATE,
                method=method,
                provider_transaction_id=result.provider_transaction_id,
                status="pending",
                card_brand=brand,
                created_at=now,
                updated_at=now,
            )
            await self.session.commit()
            if self.job_queue and result.status == "approved":
                await self.job_queue.enqueue(
                    "payment_card_confirm_job",
                    payment_id=payment.payment_id,
                    _defer_by=3,
                )
            return InitiatePaymentResponse(
                paymentId=payment.payment_id,
                transactionId=payment.payment_id,
                status=payment.status,
                sessionToken=result.session_token,
            )
        raise PaymentGatewayError(message="Unsupported payment method.")

    async def get_payment_status(
        self,
        *,
        transaction_id: str,
        client_id: str,
    ) -> PaymentStatusResponse:
        payment = await self.repo.get_by_id(transaction_id)
        if payment is None:
            raise PaymentNotFoundError()
        app = await self.apps_repo.get_by_id(payment.application_id)
        if app is None or app.client_id != client_id:
            raise PaymentNotFoundError()
        if payment.status == "processing" and payment.provider_transaction_id:
            gw_status, _ = await self.gateway.check_transaction_status(payment.provider_transaction_id)
            if gw_status == "paid":
                await self.confirm_payment(payment.payment_id, ip_address=None)
                await self.session.commit()
                payment = await self.repo.get_by_id(transaction_id)
        return PaymentStatusResponse(
            transactionId=payment.payment_id,
            status=payment.status,
            paidAt=payment.paid_at,
        )

    async def handle_card_webhook(
        self,
        *,
        provider_transaction_id: str,
        status: str,
        ip_address: str | None = None,
    ) -> None:
        from sqlalchemy import select

        from app.modules.payments.models import Payment

        payment = await self.session.scalar(
            select(Payment).where(Payment.provider_transaction_id == provider_transaction_id)
        )
        if payment is None:
            raise PaymentNotFoundError()
        if status == "paid" and payment.status != "paid":
            await self.confirm_payment(payment.payment_id, ip_address=ip_address)
            await self.session.commit()

    async def confirm_payment(
        self,
        payment_id: str,
        *,
        ip_address: str | None = None,
    ) -> None:
        payment = await self.repo.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError()
        if payment.status == "paid":
            return
        if payment.status == "timed_out":
            raise PaymentExpiredError()
        now = datetime.now(UTC)
        receipt_number = await self._generate_receipt_number()
        payment.status = "paid"
        payment.paid_at = now
        payment.receipt_number = receipt_number
        payment.updated_at = now
        app = await self.apps_repo.get_by_id(payment.application_id)
        if app is None:
            raise ApplicationNotFoundError()
        app.payment_status = "paid"
        app.payment_amount = payment.amount_rwf
        await self.messages_service.create_system_message(
            application_id=app.application_id,
            content=f"Payment of {payment.amount_rwf:,} RWF received. Receipt: {receipt_number}.",
        )
        await write_audit_entry(
            self.session,
            actor_id=None,
            actor_role=None,
            action="payment.processed",
            resource_type="payment",
            resource_id=payment.payment_id,
            details={"application_code": app.code, "amount": payment.amount_rwf},
            ip_address=ip_address,
            kind="Money",
        )
        if self.job_queue:
            client = await self.auth_repo.get_user_by_id(app.client_id)
            if client and client.email:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=client.email,
                    subject=f"Payment Confirmed — {app.code}",
                    body=(
                        f"Your payment of {payment.amount_rwf:,} RWF has been confirmed.\n"
                        f"Receipt number: {receipt_number}\n"
                        f"Application: {app.code}"
                    ),
                )

    async def get_receipt(
        self,
        *,
        application_code: str,
        client_id: str,
    ) -> PaymentReceiptResponse:
        app = await self.apps_repo.get_by_code(application_code)
        if app is None or app.client_id != client_id:
            raise ApplicationNotFoundError()
        payment = await self.repo.get_latest_for_application(app.application_id)
        if payment is None or payment.status != "paid" or payment.paid_at is None:
            raise PaymentNotFoundError()
        vat_rate = float(payment.vat_rate)
        vat_amount = int(payment.amount_rwf - payment.amount_rwf / (1 + vat_rate))
        method_label = METHOD_LABELS.get(payment.method, payment.method)
        if payment.card_brand:
            method_label = f"{payment.card_brand.title()} Card"
        return PaymentReceiptResponse(
            serviceName=app.service_name,
            trackingCode=app.code,
            amount=payment.amount_rwf,
            governmentFee=payment.government_fee_rwf,
            vatAmount=vat_amount,
            method=method_label,
            transactionId=payment.payment_id,
            receiptNumber=payment.receipt_number or "",
            paidAt=payment.paid_at,
            applicationCode=app.code,
        )

    async def _generate_receipt_number(self) -> str:
        date_part = datetime.now(UTC).strftime("%Y%m%d")
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            suffix = "".join(random.choices(alphabet, k=5))
            candidate = f"RCP-{date_part}-{suffix}"
            if not await self.repo.receipt_exists(candidate):
                return candidate
        raise RuntimeError("Failed to generate unique receipt number")
