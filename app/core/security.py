"""Security primitives shared across auth flows."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import jwt
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

from app.core.config import Settings

password_hasher = PasswordHasher()


@dataclass(slots=True)
class TokenPayload:
    subject: str
    scope: str
    expires_at: datetime
    token_id: str
    claims: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


async def async_hash_password(password: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, password_hasher.hash, password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False


async def async_verify_password(password: str, password_hash: str) -> bool:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, partial(password_hasher.verify, password_hash, password))
    except Exception:
        return False


def generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(16)}"


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_opaque_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    visible = local[:2]
    return f"{visible}•••@{domain}" if domain else f"{visible}•••"


def mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 4:
        return "+250 ••• •••"
    return f"+250 {digits[-9:-7]} ••• •••"


def create_access_token(
    *,
    settings: Settings,
    subject: str,
    claims: dict[str, Any],
    expires_in_seconds: int | None = None,
) -> tuple[str, datetime, str]:
    token_id = generate_id("atk")
    expires_at = utc_now() + timedelta(seconds=expires_in_seconds or settings.jwt_access_ttl_seconds)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": subject,
        "scope": "access",
        "jti": token_id,
        "exp": expires_at,
        "iat": utc_now(),
        **claims,
    }
    token = jwt.encode(payload, settings.jwt_access_secret, algorithm="HS256")
    return token, expires_at, token_id


def create_signed_token(
    *,
    settings: Settings,
    subject: str,
    secret: str,
    scope: str,
    expires_in_seconds: int,
    claims: dict[str, Any] | None = None,
) -> tuple[str, datetime, str]:
    token_id = generate_id(scope.replace(":", "_"))
    expires_at = utc_now() + timedelta(seconds=expires_in_seconds)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": subject,
        "scope": scope,
        "jti": token_id,
        "exp": expires_at,
        "iat": utc_now(),
        **(claims or {}),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token, expires_at, token_id


def decode_token(*, token: str, secret: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )


def encrypt_secret(value: str, settings: Settings) -> str:
    key = urlsafe_b64encode(hashlib.sha256(settings.fernet_secret.encode("utf-8")).digest())
    fernet = Fernet(key)
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str, settings: Settings) -> str:
    key = urlsafe_b64encode(hashlib.sha256(settings.fernet_secret.encode("utf-8")).digest())
    fernet = Fernet(key)
    return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
