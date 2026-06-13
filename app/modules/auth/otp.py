"""OTP generation and verification helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import pyotp
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.exceptions import OtpExpiredError, OtpWrongError, RateLimitedError
from app.core.security import generate_otp_code
from app.modules.auth.constants import OTP_REDIS_PREFIX, RESEND_REDIS_PREFIX


@dataclass(slots=True)
class OtpChallenge:
    challenge_id: str
    user_id: str
    purpose: str
    code: str
    attempts_remaining: int
    expires_at: str
    channel: str


class OtpService:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self.settings = settings
        self.redis = redis

    async def create_challenge(
        self, *, challenge_id: str, user_id: str, purpose: str, channel: str
    ) -> OtpChallenge:
        code = generate_otp_code()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.otp_ttl_seconds)
        challenge = OtpChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            purpose=purpose,
            code=code,
            attempts_remaining=self.settings.otp_max_attempts,
            expires_at=expires_at.isoformat(),
            channel=channel,
        )
        await self.redis.setex(
            self._otp_key(challenge_id),
            self.settings.otp_ttl_seconds,
            json.dumps(asdict(challenge)),
        )
        return challenge

    async def resend_challenge(
        self,
        *,
        challenge_id: str,
        user_id: str,
        purpose: str,
        channel: str,
    ) -> OtpChallenge:
        cooldown_key = self._resend_key(challenge_id)
        exists = await self.redis.get(cooldown_key)
        if exists:
            raise RateLimitedError(retry_after_seconds=self.settings.otp_resend_cooldown_seconds)
        await self.redis.setex(cooldown_key, self.settings.otp_resend_cooldown_seconds, "cooldown")
        return await self.create_challenge(
            challenge_id=challenge_id,
            user_id=user_id,
            purpose=purpose,
            channel=channel,
        )

    async def verify_challenge(self, *, challenge_id: str, submitted_code: str) -> OtpChallenge:
        payload_raw = await self.redis.get(self._otp_key(challenge_id))
        if payload_raw is None:
            raise OtpExpiredError()

        challenge = OtpChallenge(**json.loads(payload_raw))
        if challenge.code != submitted_code:
            challenge.attempts_remaining -= 1
            if challenge.attempts_remaining <= 0:
                await self.redis.delete(self._otp_key(challenge_id))
                raise OtpWrongError(attempts_remaining=0)
            remaining_ttl = await self.redis.ttl(self._otp_key(challenge_id))
            await self.redis.setex(
                self._otp_key(challenge_id),
                max(remaining_ttl, 1),
                json.dumps(asdict(challenge)),
            )
            raise OtpWrongError(attempts_remaining=challenge.attempts_remaining)

        await self.redis.delete(self._otp_key(challenge_id))
        return challenge

    @staticmethod
    def verify_totp(*, secret: str, submitted_code: str) -> bool:
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(submitted_code, valid_window=1))

    @staticmethod
    def generate_totp_secret() -> str:
        return pyotp.random_base32()

    def _otp_key(self, challenge_id: str) -> str:
        return f"{OTP_REDIS_PREFIX}:{challenge_id}"

    def _resend_key(self, challenge_id: str) -> str:
        return f"{RESEND_REDIS_PREFIX}:{challenge_id}"
