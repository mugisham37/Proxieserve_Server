"""Application exception hierarchy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AppError(Exception):
    """Base class for errors that map to the frontend envelope."""

    def __init__(
        self,
        *,
        message: str,
        error_type: str,
        status_code: int,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.data = dict(data or {})


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Incorrect email, phone, or password.",
            error_type="invalid-credentials",
            status_code=401,
        )


class AccountLockedError(AppError):
    def __init__(self, *, lockout_until: str) -> None:
        super().__init__(
            message="Account temporarily locked.",
            error_type="account-locked",
            status_code=423,
            data={"lockoutUntil": lockout_until},
        )


class AccountExistsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="An account with this identifier already exists.",
            error_type="account-exists",
            status_code=409,
        )


class OtpWrongError(AppError):
    def __init__(self, *, attempts_remaining: int) -> None:
        super().__init__(
            message="Incorrect verification code.",
            error_type="otp-wrong",
            status_code=401,
            data={"attemptsRemaining": attempts_remaining},
        )


class OtpExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Verification code has expired.",
            error_type="otp-expired",
            status_code=410,
        )


class ResetExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Reset token is invalid or expired.",
            error_type="reset-expired",
            status_code=410,
        )


class ClaimNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Application not found for that PRX code.",
            error_type="claim-not-found",
            status_code=404,
        )


class RateLimitedError(AppError):
    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__(
            message="Too many requests. Try again shortly.",
            error_type="rate-limited",
            status_code=429,
            data={"retryAfterSeconds": retry_after_seconds},
        )


class UnauthorizedError(AppError):
    def __init__(self, *, message: str = "Authentication required.") -> None:
        super().__init__(message=message, error_type="unauthorized", status_code=401)
