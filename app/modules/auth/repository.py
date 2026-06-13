"""Persistence helpers for the auth module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import (
    BackupCode,
    LoginAttempt,
    PasswordResetToken,
    RefreshToken,
    StaffProfile,
    TermsAcceptance,
    TrustedDevice,
    User,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return cast(User | None, await self.session.scalar(select(User).where(User.email == email)))

    async def get_user_by_phone(self, phone_e164: str) -> User | None:
        return cast(
            User | None,
            await self.session.scalar(select(User).where(User.phone_e164 == phone_e164)),
        )

    async def get_user_by_identifier(self, *, identifier_type: str, identifier: str) -> User | None:
        if identifier_type == "email":
            return await self.get_user_by_email(identifier)
        return await self.get_user_by_phone(identifier)

    async def create_user(self, **kwargs: object) -> User:
        user = User(**kwargs)
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_staff_profile(self, **kwargs: object) -> StaffProfile:
        profile = StaffProfile(**kwargs)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_staff_profile(self, user_id: str) -> StaffProfile | None:
        return await self.session.get(StaffProfile, user_id)

    async def create_refresh_token(self, **kwargs: object) -> RefreshToken:
        token = RefreshToken(**kwargs)
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        return cast(
            RefreshToken | None,
            await self.session.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            ),
        )

    async def mark_refresh_token_replaced(
        self, *, token_id: str, replaced_by_token_id: str
    ) -> None:
        token = await self.session.get(RefreshToken, token_id)
        if token is None:
            return
        token.replaced_by_token_id = replaced_by_token_id
        token.revoked_at = utc_now()
        await self.session.flush()

    async def revoke_refresh_family(self, family_id: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )

    async def delete_refresh_tokens_for_user(self, user_id: str) -> None:
        result = await self.session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        for token in result:
            token.revoked_at = utc_now()
        await self.session.flush()

    async def create_password_reset_token(self, **kwargs: object) -> PasswordResetToken:
        token = PasswordResetToken(**kwargs)
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_password_reset_token_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt: Select[tuple[PasswordResetToken]] = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        return cast(PasswordResetToken | None, await self.session.scalar(stmt))

    async def mark_reset_token_used(self, token_id: str) -> None:
        token = await self.session.get(PasswordResetToken, token_id)
        if token is None:
            return
        token.used_at = utc_now()
        await self.session.flush()

    async def create_terms_acceptance(self, **kwargs: object) -> TermsAcceptance:
        acceptance = TermsAcceptance(**kwargs)
        self.session.add(acceptance)
        await self.session.flush()
        return acceptance

    async def record_login_attempt(self, **kwargs: object) -> LoginAttempt:
        attempt = LoginAttempt(**kwargs)
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def create_trusted_device(self, **kwargs: object) -> TrustedDevice:
        device = TrustedDevice(**kwargs)
        self.session.add(device)
        await self.session.flush()
        return device

    async def get_trusted_device(
        self, *, user_id: str, fingerprint_hash: str
    ) -> TrustedDevice | None:
        stmt = select(TrustedDevice).where(
            TrustedDevice.user_id == user_id,
            TrustedDevice.fingerprint_hash == fingerprint_hash,
        )
        return cast(TrustedDevice | None, await self.session.scalar(stmt))

    async def list_active_backup_codes(self, user_id: str) -> list[BackupCode]:
        stmt = select(BackupCode).where(BackupCode.user_id == user_id, BackupCode.used_at.is_(None))
        result = await self.session.scalars(stmt)
        return list(result)

    async def mark_backup_code_used(self, backup_code_id: str) -> None:
        code = await self.session.get(BackupCode, backup_code_id)
        if code is None:
            return
        code.used_at = utc_now()
        await self.session.flush()
