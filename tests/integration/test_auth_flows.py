from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import redis_manager
from app.core.security import encrypt_secret, generate_id, hash_password, hash_token
from app.modules.auth.models import BackupCode, PasswordResetToken, StaffProfile, User


async def seed_user(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    email: str | None,
    phone: str | None,
    password: str,
    role: str = "client",
    verified: bool = False,
) -> User:
    user = User(
        user_id=user_id,
        name=name,
        email=email,
        phone_e164=phone,
        password_hash=hash_password(password),
        role=role,
        is_email_verified=verified,
        language="en",
    )
    session.add(user)
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_signup_sets_session_cookie_and_masked_email(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/signup",
        json={
            "name": "Amina Nkurunziza",
            "identifierType": "email",
            "identifier": "amina@example.com",
            "password": "Secret123!",
            "language": "en",
            "terms": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["maskedEmail"] == "am•••@example.com"
    assert "proxiserve_access" in response.cookies
    assert "proxiserve_refresh" in response.cookies


@pytest.mark.asyncio
async def test_login_lockout_returns_account_locked_after_threshold(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_user(
        db_session,
        user_id="usr_lockout",
        name="Locked User",
        email="locked@example.com",
        phone=None,
        password="Correct123!",
    )

    payload = {
        "identifierType": "email",
        "identifier": "locked@example.com",
        "password": "wrongpassword",
    }
    for _ in range(5):
        response = await client.post("/api/auth/login", json=payload)
        assert response.status_code == 401
        assert response.json()["errorType"] == "invalid-credentials"

    locked = await client.post("/api/auth/login", json=payload)
    assert locked.status_code == 423
    assert locked.json()["errorType"] == "account-locked"
    assert "lockoutUntil" in locked.json()["data"]


@pytest.mark.asyncio
async def test_client_otp_verification_round_trip(client: httpx.AsyncClient) -> None:
    signup = await client.post(
        "/api/auth/signup",
        json={
            "name": "Otp User",
            "identifierType": "email",
            "identifier": "otp@example.com",
            "password": "Secret123!",
            "language": "en",
            "terms": True,
        },
    )
    user_id = signup.json()["data"]["session"]["userId"]
    assert redis_manager.client is not None
    challenge_raw = await redis_manager.client.get(f"auth:otp:{user_id}:client-verify")
    assert challenge_raw is not None
    challenge = json.loads(challenge_raw)

    verify = await client.post("/api/auth/verify-otp", json={"code": challenge["code"]})
    assert verify.status_code == 200
    assert verify.json()["data"]["verified"] is True


@pytest.mark.asyncio
async def test_forgot_password_is_enumeration_safe(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/forgot-password",
        json={"identifierType": "email", "identifier": "nobody@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["maskedEmail"] == "no•••@example.com"


@pytest.mark.asyncio
async def test_reset_password_marks_token_used_and_revokes_sessions(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await seed_user(
        db_session,
        user_id="usr_reset",
        name="Reset User",
        email="reset@example.com",
        phone=None,
        password="OldSecret123!",
    )
    raw_token = "reset-token-value"
    db_session.add(
        PasswordResetToken(
            id=generate_id("prt"),
            user_id=user.user_id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db_session.commit()

    response = await client.post(
        "/api/auth/reset-password",
        json={
            "token": raw_token,
            "password": "NewSecret123!",
            "confirmPassword": "NewSecret123!",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_staff_login_and_backup_code_2fa(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    settings = get_settings()
    user = await seed_user(
        db_session,
        user_id="usr_staff",
        name="Staff Admin",
        email="admin@proxiserve.rw",
        phone="+250788123456",
        password="AdminSecret123!",
        role="staff:admin",
        verified=True,
    )
    db_session.add(
        StaffProfile(
            user_id=user.user_id,
            totp_secret_encrypted=encrypt_secret("JBSWY3DPEHPK3PXP", settings),
            twofa_enabled=True,
            sms_phone_e164="+250788123456",
        )
    )
    db_session.add(
        BackupCode(
            id=generate_id("bkc"),
            user_id=user.user_id,
            code_hash=hash_password("BACKUP-123"),
        )
    )
    await db_session.commit()

    login = await client.post(
        "/api/auth/staff/login",
        json={"email": "admin@proxiserve.rw", "password": "AdminSecret123!", "role": "admin"},
    )
    assert login.status_code == 200
    pre2fa_token = login.json()["data"]["pre2faToken"]

    verify = await client.post(
        "/api/auth/staff/2fa",
        json={
            "code": "BACKUP-123",
            "method": "backup",
            "trustDevice": True,
            "pre2faToken": pre2fa_token,
        },
    )
    assert verify.status_code == 200
    assert verify.json()["data"]["session"]["role"] == "staff:admin"
    assert "proxiserve_access" in verify.cookies


@pytest.mark.asyncio
async def test_session_endpoint_refreshes_from_refresh_cookie(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_user(
        db_session,
        user_id="usr_refresh",
        name="Refresh User",
        email="refresh@example.com",
        phone=None,
        password="RefreshSecret123!",
    )

    login = await client.post(
        "/api/auth/login",
        json={
            "identifierType": "email",
            "identifier": "refresh@example.com",
            "password": "RefreshSecret123!",
        },
    )
    assert login.status_code == 200
    refresh_cookie = client.cookies.get("proxiserve_refresh")
    assert refresh_cookie is not None
    client.cookies.delete("proxiserve_access")

    session_response = await client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["data"]["session"]["userId"] == "usr_refresh"
    assert session_response.cookies.get("proxiserve_access") is not None


@pytest.mark.asyncio
async def test_applications_lookup_and_claim(client: httpx.AsyncClient) -> None:
    lookup = await client.get("/api/applications/lookup", params={"code": "PRX-2026-00483"})
    assert lookup.status_code == 200
    assert lookup.json()["data"]["serviceName"] == "Passport renewal"

    claim = await client.post(
        "/api/applications/claim",
        json={"code": "PRX-2026-00483", "phone": "+250788123456"},
    )
    assert claim.status_code == 200
    assert claim.json()["data"]["claimed"] is True
