"""Authentication service orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Generic, TypeVar, cast

import phonenumbers
from pydantic import EmailStr, TypeAdapter
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.events import EventBus
from app.core.exceptions import (
    AccountExistsError,
    AccountLockedError,
    InvalidCredentialsError,
    OtpWrongError,
    ResetExpiredError,
    UnauthorizedError,
)
from app.core.jobs import JobQueueManager
from app.core.security import (
    generate_id,
    generate_opaque_token,
    hash_password,
    hash_token,
    mask_email,
    mask_phone,
    verify_password,
)
from app.modules.auth.events import ApplicationClaimRequested, UserRegistered
from app.modules.auth.models import User
from app.modules.auth.otp import OtpService
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    AuthFlowData,
    AuthLanguage,
    AuthSessionModel,
    ForgotPasswordData,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SessionData,
    SignOutData,
    SignupRequest,
    StaffLoginData,
    StaffLoginRequest,
    StaffTwoFactorRequest,
    VerifyOtpData,
    VerifyOtpRequest,
)
from app.modules.auth.tokens import SessionTokenBundle, TokenService

PayloadT = TypeVar("PayloadT")


@dataclass(slots=True)
class ServiceResult(Generic[PayloadT]):
    payload: PayloadT
    token_bundle: SessionTokenBundle | None = None


class AuthService:
    """Primary auth orchestration layer."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        settings: Settings,
        event_bus: EventBus,
        job_queue: JobQueueManager,
    ) -> None:
        self.session = session
        self.redis = redis
        self.settings = settings
        self.event_bus = event_bus
        self.job_queue = job_queue
        self.repository = AuthRepository(session)
        self.otp_service = OtpService(settings, redis)
        self.token_service = TokenService(settings, redis)

    async def signup(
        self,
        request: SignupRequest,
        *,
        ip_address: str | None,
    ) -> ServiceResult[AuthFlowData]:
        normalized_identifier = self._normalize_identifier(request.identifierType, request.identifier)
        existing = await self.repository.get_user_by_identifier(
            identifier_type=request.identifierType,
            identifier=normalized_identifier,
        )
        if existing is not None:
            raise AccountExistsError()

        user_id = generate_id("usr")
        email = normalized_identifier if request.identifierType == "email" else None
        phone = normalized_identifier if request.identifierType == "phone" else None
        user = await self.repository.create_user(
            user_id=user_id,
            name=request.name,
            email=email,
            phone_e164=phone,
            password_hash=hash_password(request.password),
            role="client",
            is_email_verified=False,
            language=request.language,
        )
        await self.repository.create_terms_acceptance(
            id=generate_id("terms"),
            user_id=user.user_id,
            policy_version="2026-05-auth-bootstrap",
        )
        await self.repository.record_login_attempt(
            id=generate_id("lat"),
            identifier=normalized_identifier,
            ip_address=ip_address,
            success=True,
        )

        bundle = await self._issue_session_for_user(user, is_staff=False)
        challenge_id = self._client_challenge_id(user.user_id)
        await self.otp_service.create_challenge(
            challenge_id=challenge_id,
            user_id=user.user_id,
            purpose="client-verify",
            channel="email" if email else "sms",
        )
        await self._enqueue_otp_notification(
            email=email,
            phone=phone,
            code_preview="verification code",
        )

        await self.session.commit()
        await self.event_bus.publish(UserRegistered(user_id=user.user_id, identifier=normalized_identifier).to_domain_event())
        if request.code:
            await self.event_bus.publish(
                ApplicationClaimRequested(user_id=user.user_id, code=request.code, phone=phone or "").to_domain_event()
            )

        return ServiceResult(
            payload=AuthFlowData(
                session=self._session_model(user, bundle.access_expires_at),
                maskedEmail=self._masked_identifier(email=email, phone=phone),
            ),
            token_bundle=bundle,
        )

    async def login(
        self,
        request: LoginRequest,
        *,
        ip_address: str | None,
    ) -> ServiceResult[AuthFlowData]:
        normalized_identifier = self._normalize_identifier(request.identifierType, request.identifier)
        await self._assert_not_locked(identifier=normalized_identifier, ip_address=ip_address)

        user = await self.repository.get_user_by_identifier(
            identifier_type=request.identifierType,
            identifier=normalized_identifier,
        )
        if user is None or not verify_password(request.password, user.password_hash):
            await self._record_login_failure(identifier=normalized_identifier, ip_address=ip_address)
            raise InvalidCredentialsError()

        await self._clear_lockout(identifier=normalized_identifier, ip_address=ip_address)
        await self.repository.record_login_attempt(
            id=generate_id("lat"),
            identifier=normalized_identifier,
            ip_address=ip_address,
            success=True,
        )

        bundle = await self._issue_session_for_user(user, is_staff=False)
        await self.otp_service.create_challenge(
            challenge_id=self._client_challenge_id(user.user_id),
            user_id=user.user_id,
            purpose="client-verify",
            channel="email" if user.email else "sms",
        )
        await self._enqueue_otp_notification(
            email=user.email,
            phone=user.phone_e164,
            code_preview="verification code",
        )
        await self.session.commit()

        return ServiceResult(
            payload=AuthFlowData(
                session=self._session_model(user, bundle.access_expires_at),
                maskedEmail=self._masked_identifier(email=user.email, phone=user.phone_e164),
            ),
            token_bundle=bundle,
        )

    async def verify_client_otp(
        self,
        request: VerifyOtpRequest,
        *,
        current_user_id: str,
    ) -> ServiceResult[VerifyOtpData]:
        await self.otp_service.verify_challenge(
            challenge_id=self._client_challenge_id(current_user_id),
            submitted_code=request.code,
        )
        user = await self.repository.get_user_by_id(current_user_id)
        if user is None:
            raise UnauthorizedError()
        user.is_email_verified = True
        await self.session.commit()
        return ServiceResult(payload=VerifyOtpData())

    async def resend_client_otp(self, *, current_user_id: str) -> ServiceResult[VerifyOtpData]:
        user = await self.repository.get_user_by_id(current_user_id)
        if user is None:
            raise UnauthorizedError()
        await self.otp_service.resend_challenge(
            challenge_id=self._client_challenge_id(current_user_id),
            user_id=current_user_id,
            purpose="client-verify",
            channel="email" if user.email else "sms",
        )
        await self._enqueue_otp_notification(
            email=user.email,
            phone=user.phone_e164,
            code_preview="verification code",
        )
        return ServiceResult(payload=VerifyOtpData())

    async def forgot_password(
        self,
        request: ForgotPasswordRequest,
    ) -> ServiceResult[ForgotPasswordData]:
        normalized_identifier = self._normalize_identifier(request.identifierType, request.identifier)
        user = await self.repository.get_user_by_identifier(
            identifier_type=request.identifierType,
            identifier=normalized_identifier,
        )
        if user is not None:
            reset_token = generate_opaque_token("rst")
            await self.repository.create_password_reset_token(
                id=generate_id("prt"),
                user_id=user.user_id,
                token_hash=hash_token(reset_token),
                expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.password_reset_ttl_seconds),
            )
            await self._enqueue_reset_notification(
                email=user.email,
                phone=user.phone_e164,
                token=reset_token,
            )
            await self.session.commit()

        return ServiceResult(
            payload=ForgotPasswordData(maskedEmail=self._masked_identifier_value(request.identifierType, normalized_identifier))
        )

    async def reset_password(
        self,
        request: ResetPasswordRequest,
    ) -> ServiceResult[VerifyOtpData]:
        token_hash_value = hash_token(request.token)
        reset_token = await self.repository.get_password_reset_token_by_hash(token_hash_value)
        if reset_token is None or reset_token.used_at is not None or reset_token.expires_at < datetime.now(UTC):
            raise ResetExpiredError()

        user = await self.repository.get_user_by_id(reset_token.user_id)
        if user is None:
            raise ResetExpiredError()
        user.password_hash = hash_password(request.password)
        await self.repository.mark_reset_token_used(reset_token.id)
        await self.repository.delete_refresh_tokens_for_user(user.user_id)
        await self.session.commit()
        return ServiceResult(payload=VerifyOtpData())

    async def sign_out(self, *, refresh_token: str | None) -> ServiceResult[SignOutData]:
        if refresh_token:
            refresh_payload = await self.token_service.validate_refresh_token(refresh_token)
            if refresh_payload is not None:
                await self.repository.revoke_refresh_family(refresh_payload["familyId"])
                await self.token_service.revoke_refresh_family(refresh_payload["familyId"])
                await self.session.commit()
        return ServiceResult(payload=SignOutData())

    async def staff_login(
        self,
        request: StaffLoginRequest,
        *,
        ip_address: str | None,
    ) -> ServiceResult[StaffLoginData]:
        user = await self.repository.get_user_by_email(str(request.email).lower())
        expected_role = "staff:admin" if request.role == "admin" else "staff:agent"
        if user is None or user.role != expected_role or not verify_password(request.password, user.password_hash):
            raise InvalidCredentialsError()

        staff_profile = await self.repository.get_staff_profile(user.user_id)
        sms_challenge_id = self._staff_sms_challenge_id(user.user_id)
        await self.otp_service.create_challenge(
            challenge_id=sms_challenge_id,
            user_id=user.user_id,
            purpose="staff-2fa-sms",
            channel="sms",
        )
        await self._enqueue_otp_notification(
            email=None,
            phone=staff_profile.sms_phone_e164 if staff_profile else user.phone_e164,
            code_preview="staff SMS code",
        )
        pre2fa_token, _, _ = await self.token_service.issue_pre_2fa_token(
            subject=user.user_id,
            claims={"role": user.role, "smsChallengeId": sms_challenge_id},
        )
        await self.repository.record_login_attempt(
            id=generate_id("lat"),
            identifier=str(request.email).lower(),
            ip_address=ip_address,
            success=True,
        )
        await self.session.commit()
        return ServiceResult(
            payload=StaffLoginData(
                session=self._session_model(user, None),
                pre2faToken=pre2fa_token,
            )
        )

    async def staff_two_factor(
        self,
        request: StaffTwoFactorRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ServiceResult[SessionData]:
        token_payload = await self.token_service.consume_pre_2fa_token(request.pre2faToken)
        user = await self.repository.get_user_by_id(token_payload["sub"])
        if user is None:
            raise UnauthorizedError()

        staff_profile = await self.repository.get_staff_profile(user.user_id)
        if request.method == "totp":
            if staff_profile is None or staff_profile.totp_secret_encrypted is None:
                raise OtpWrongError(attempts_remaining=0)
            from app.core.security import decrypt_secret

            secret = decrypt_secret(staff_profile.totp_secret_encrypted, self.settings)
            if not self.otp_service.verify_totp(secret=secret, submitted_code=request.code):
                raise OtpWrongError(attempts_remaining=0)
        elif request.method == "sms":
            await self.otp_service.verify_challenge(
                challenge_id=self._staff_sms_challenge_id(user.user_id),
                submitted_code=request.code,
            )
        else:
            await self._consume_backup_code(user.user_id, request.code)

        bundle = await self._issue_session_for_user(user, is_staff=True)

        if request.trustDevice:
            fingerprint = self.token_service.build_device_fingerprint(user_agent=user_agent, ip_address=ip_address)
            existing = await self.repository.get_trusted_device(user_id=user.user_id, fingerprint_hash=fingerprint)
            trusted_until = datetime.now(UTC) + timedelta(seconds=self.settings.trusted_device_ttl_seconds)
            if existing is None:
                await self.repository.create_trusted_device(
                    id=generate_id("tdv"),
                    user_id=user.user_id,
                    fingerprint_hash=fingerprint,
                    trusted_until=trusted_until,
                )
            else:
                existing.trusted_until = trusted_until
            await self.token_service.remember_device(user_id=user.user_id, fingerprint=fingerprint)

        await self.session.commit()
        return ServiceResult(
            payload=SessionData(session=self._session_model(user, bundle.access_expires_at)),
            token_bundle=bundle,
        )

    async def _enqueue_otp_notification(
        self,
        *,
        email: str | None,
        phone: str | None,
        code_preview: str,
    ) -> None:
        if email:
            await self.job_queue.enqueue(
                "send_email_job",
                to=email,
                subject="Your ProxiServe verification code",
                body=f"Your {code_preview} has been generated.",
            )
        elif phone:
            await self.job_queue.enqueue(
                "send_sms_job",
                to=phone,
                body=f"Your {code_preview} has been generated.",
            )

    async def _enqueue_reset_notification(
        self,
        *,
        email: str | None,
        phone: str | None,
        token: str,
    ) -> None:
        body = f"Use this reset token to complete your password reset: {token}"
        if email:
            await self.job_queue.enqueue(
                "send_email_job",
                to=email,
                subject="Reset your ProxiServe password",
                body=body,
            )
        elif phone:
            await self.job_queue.enqueue("send_sms_job", to=phone, body=body)

    async def get_session(
        self,
        *,
        current_user_id: str,
        expires_at: datetime | None,
    ) -> ServiceResult[SessionData]:
        user = await self.repository.get_user_by_id(current_user_id)
        if user is None:
            raise UnauthorizedError()
        return ServiceResult(payload=SessionData(session=self._session_model(user, expires_at)))

    async def refresh_session(self, *, refresh_token: str) -> ServiceResult[SessionData]:
        refresh_payload = await self.token_service.validate_refresh_token(refresh_token)
        if refresh_payload is None:
            raise UnauthorizedError()
        user = await self.repository.get_user_by_id(refresh_payload["userId"])
        if user is None:
            raise UnauthorizedError()
        bundle = await self._issue_session_for_user(user, is_staff=user.role.startswith("staff:"))
        await self.repository.revoke_refresh_family(refresh_payload["familyId"])
        await self.token_service.revoke_refresh_family(refresh_payload["familyId"])
        await self.session.commit()
        return ServiceResult(
            payload=SessionData(session=self._session_model(user, bundle.access_expires_at)),
            token_bundle=bundle,
        )

    async def _issue_session_for_user(self, user: User, *, is_staff: bool) -> SessionTokenBundle:
        bundle = await self.token_service.issue_session_bundle(
            subject=user.user_id,
            claims={
                "role": user.role,
                "isEmailVerified": user.is_email_verified,
                "language": user.language,
            },
            is_staff=is_staff,
        )
        await self.repository.create_refresh_token(
            id=bundle.refresh_token_id,
            user_id=user.user_id,
            family_id=bundle.refresh_family_id,
            token_hash=hash_token(bundle.refresh_token),
            expires_at=bundle.refresh_expires_at,
        )
        return bundle

    async def _record_login_failure(self, *, identifier: str, ip_address: str | None) -> None:
        await self.repository.record_login_attempt(
            id=generate_id("lat"),
            identifier=identifier,
            ip_address=ip_address,
            success=False,
        )
        attempts_key = self._lockout_attempts_key(identifier, ip_address)
        current = await self.redis.incr(attempts_key)
        if current == 1:
            await self.redis.expire(attempts_key, self.settings.lockout_window_seconds)
        if current >= self.settings.lockout_max_attempts:
            until = datetime.now(UTC) + timedelta(seconds=self.settings.lockout_window_seconds)
            await self.redis.setex(self._lockout_until_key(identifier, ip_address), self.settings.lockout_window_seconds, until.isoformat())
        await self.session.commit()

    async def _assert_not_locked(self, *, identifier: str, ip_address: str | None) -> None:
        until = await self.redis.get(self._lockout_until_key(identifier, ip_address))
        if until:
            raise AccountLockedError(lockout_until=until)

    async def _clear_lockout(self, *, identifier: str, ip_address: str | None) -> None:
        await self.redis.delete(self._lockout_attempts_key(identifier, ip_address))
        await self.redis.delete(self._lockout_until_key(identifier, ip_address))

    async def _consume_backup_code(self, user_id: str, code: str) -> None:
        backup_codes = await self.repository.list_active_backup_codes(user_id)
        for backup_code in backup_codes:
            if verify_password(code, backup_code.code_hash):
                await self.repository.mark_backup_code_used(backup_code.id)
                return
        raise OtpWrongError(attempts_remaining=0)

    def _normalize_identifier(self, identifier_type: str, identifier: str) -> str:
        if identifier_type == "email":
            return str(TypeAdapter(EmailStr).validate_python(identifier)).lower()
        try:
            parsed = phonenumbers.parse(identifier, "RW")
        except phonenumbers.NumberParseException as exc:  # pragma: no cover - defensive
            raise InvalidCredentialsError() from exc
        if not phonenumbers.is_valid_number_for_region(parsed, "RW"):
            raise InvalidCredentialsError()
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    def _session_model(self, user: User, expires_at: datetime | None) -> AuthSessionModel:
        # The frontend currently requires a non-null `email` field, so phone-first
        # accounts fall back to their phone identifier until the contract is widened.
        email_value = user.email or user.phone_e164 or ""
        return AuthSessionModel(
            userId=user.user_id,
            name=user.name,
            email=email_value,
            phone=user.phone_e164,
            role=user.role,
            isEmailVerified=user.is_email_verified,
            language=cast(AuthLanguage, user.language),
            createdAt=user.created_at.isoformat(),
            expiresAt=expires_at.isoformat() if expires_at else None,
        )

    def _masked_identifier(self, *, email: str | None, phone: str | None) -> str:
        if email:
            return mask_email(email)
        if phone:
            return mask_phone(phone)
        return "your account"

    def _masked_identifier_value(self, identifier_type: str, value: str) -> str:
        if identifier_type == "email":
            return mask_email(value)
        return mask_phone(value)

    @staticmethod
    def _client_challenge_id(user_id: str) -> str:
        return f"{user_id}:client-verify"

    @staticmethod
    def _staff_sms_challenge_id(user_id: str) -> str:
        return f"{user_id}:staff-sms"

    @staticmethod
    def _lockout_attempts_key(identifier: str, ip_address: str | None) -> str:
        return f"auth:lockout:attempts:{hash_token(identifier)}:{hash_token(ip_address or 'unknown')}"

    @staticmethod
    def _lockout_until_key(identifier: str, ip_address: str | None) -> str:
        return f"auth:lockout:until:{hash_token(identifier)}:{hash_token(ip_address or 'unknown')}"
