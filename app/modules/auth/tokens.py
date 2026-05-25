"""Token lifecycle helpers for the auth module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, cast

from fastapi import Response
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_signed_token,
    decode_token,
    generate_id,
    generate_opaque_token,
    hash_token,
)
from app.modules.auth.constants import (
    ACCESS_COOKIE_NAME,
    DEVICE_TRUST_REDIS_PREFIX,
    PRE_2FA_REDIS_PREFIX,
    REFRESH_COOKIE_NAME,
    REFRESH_REDIS_PREFIX,
)


@dataclass(slots=True)
class SessionTokenBundle:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    refresh_token_id: str
    refresh_family_id: str


@dataclass(slots=True)
class RefreshTokenRecord:
    token_id: str
    family_id: str
    token_hash: str
    expires_at: datetime


class TokenService:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self.settings = settings
        self.redis = redis

    async def issue_session_bundle(
        self,
        *,
        subject: str,
        claims: dict[str, Any],
        is_staff: bool = False,
    ) -> SessionTokenBundle:
        access_token, access_expires_at, _ = create_access_token(
            settings=self.settings,
            subject=subject,
            claims=claims,
        )
        refresh_token = generate_opaque_token("rft")
        refresh_token_id = generate_id("rti")
        refresh_family_id = generate_id("rtf")
        refresh_expires_at = datetime.now(UTC).replace(microsecond=0)
        ttl_seconds = (
            self.settings.jwt_staff_refresh_ttl_seconds if is_staff else self.settings.jwt_refresh_ttl_seconds
        )
        refresh_expires_at = refresh_expires_at + timedelta(seconds=ttl_seconds)
        refresh_record = {
            "userId": subject,
            "familyId": refresh_family_id,
            "tokenId": refresh_token_id,
            "expiresAt": refresh_expires_at.isoformat(),
            "role": claims.get("role"),
        }
        await self.redis.setex(
            self._refresh_key(hash_token(refresh_token)),
            ttl_seconds,
            json.dumps(refresh_record),
        )
        return SessionTokenBundle(
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_expires_at,
            refresh_token_id=refresh_token_id,
            refresh_family_id=refresh_family_id,
        )

    async def validate_refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        token_hash = hash_token(refresh_token)
        payload_raw = await self.redis.get(self._refresh_key(token_hash))
        if payload_raw is None:
            return None
        payload = cast(dict[str, Any], json.loads(payload_raw))
        family_revoked = await self.redis.get(self._refresh_family_revoked_key(payload["familyId"]))
        if family_revoked:
            return None
        return payload

    async def rotate_refresh_token(
        self,
        *,
        refresh_token: str,
        subject: str,
        claims: dict[str, Any],
        is_staff: bool = False,
    ) -> SessionTokenBundle | None:
        current = await self.validate_refresh_token(refresh_token)
        if current is None:
            return None

        token_hash = hash_token(refresh_token)
        await self.redis.delete(self._refresh_key(token_hash))
        bundle = await self.issue_session_bundle(subject=subject, claims=claims, is_staff=is_staff)
        await self.redis.setex(
            self._refresh_family_revoked_key(current["familyId"]),
            5,
            "rotated",
        )
        await self.redis.delete(self._refresh_family_revoked_key(current["familyId"]))
        return bundle

    async def revoke_refresh_family(self, family_id: str, ttl_seconds: int = 86400) -> None:
        await self.redis.setex(self._refresh_family_revoked_key(family_id), ttl_seconds, "revoked")

    async def issue_pre_2fa_token(
        self,
        *,
        subject: str,
        claims: dict[str, Any],
    ) -> tuple[str, datetime, str]:
        token, expires_at, token_id = create_signed_token(
            settings=self.settings,
            subject=subject,
            secret=self.settings.jwt_pre_2fa_secret,
            scope="staff-pre-2fa",
            expires_in_seconds=self.settings.jwt_pre_2fa_ttl_seconds,
            claims=claims,
        )
        await self.redis.setex(self._pre_2fa_key(token_id), self.settings.jwt_pre_2fa_ttl_seconds, "active")
        return token, expires_at, token_id

    async def consume_pre_2fa_token(self, token: str) -> dict[str, Any]:
        payload = decode_token(token=token, secret=self.settings.jwt_pre_2fa_secret, settings=self.settings)
        token_id = payload["jti"]
        key = self._pre_2fa_key(token_id)
        was_active = await self.redis.get(key)
        if was_active is None:
            raise ValueError("Pre-2FA token is missing or already consumed")
        await self.redis.delete(key)
        return payload

    def apply_session_cookies(self, response: Response, bundle: SessionTokenBundle) -> None:
        same_site = cast(Literal["lax", "strict", "none"], self.settings.cookie_samesite)
        response.set_cookie(
            key=ACCESS_COOKIE_NAME,
            value=bundle.access_token,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite=same_site,
            domain=self.settings.cookie_domain,
            expires=bundle.access_expires_at,
            path="/",
        )
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=bundle.refresh_token,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite=same_site,
            domain=self.settings.cookie_domain,
            expires=bundle.refresh_expires_at,
            path="/",
        )

    def clear_session_cookies(self, response: Response) -> None:
        response.delete_cookie(ACCESS_COOKIE_NAME, path="/", domain=self.settings.cookie_domain)
        response.delete_cookie(REFRESH_COOKIE_NAME, path="/", domain=self.settings.cookie_domain)

    async def remember_device(self, *, user_id: str, fingerprint: str) -> None:
        await self.redis.setex(
            self._device_trust_key(user_id, fingerprint),
            self.settings.trusted_device_ttl_seconds,
            "trusted",
        )

    async def is_trusted_device(self, *, user_id: str, fingerprint: str) -> bool:
        return bool(await self.redis.get(self._device_trust_key(user_id, fingerprint)))

    @staticmethod
    def build_device_fingerprint(*, user_agent: str | None, ip_address: str | None) -> str:
        raw = f"{user_agent or 'unknown'}|{ip_address or 'unknown'}"
        return sha256(raw.encode("utf-8")).hexdigest()

    def _refresh_key(self, token_hash_value: str) -> str:
        return f"{REFRESH_REDIS_PREFIX}:token:{token_hash_value}"

    def _refresh_family_revoked_key(self, family_id: str) -> str:
        return f"{REFRESH_REDIS_PREFIX}:family:{family_id}:revoked"

    def _pre_2fa_key(self, token_id: str) -> str:
        return f"{PRE_2FA_REDIS_PREFIX}:{token_id}"

    def _device_trust_key(self, user_id: str, fingerprint: str) -> str:
        return f"{DEVICE_TRUST_REDIS_PREFIX}:{user_id}:{fingerprint}"
