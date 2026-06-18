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


class ForbiddenError(AppError):
    def __init__(
        self, *, message: str = "You do not have permission to access this resource."
    ) -> None:
        super().__init__(message=message, error_type="forbidden", status_code=403)


class AgentNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(message="Agent not found.", error_type="agent-not-found", status_code=404)


class EmailAlreadyInUseError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="An account with that email address already exists.",
            error_type="email-already-in-use",
            status_code=409,
        )


class ServiceNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Service not found.",
            error_type="service-not-found",
            status_code=404,
        )


class ServiceSlugConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="A service with this slug already exists.",
            error_type="service-slug-conflict",
            status_code=409,
        )


class ApplicationNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Application not found.",
            error_type="application-not-found",
            status_code=404,
        )


class ApplicationAccessForbiddenError(AppError):
    def __init__(self, *, code: str | None = None) -> None:
        data = {"code": code} if code else None
        super().__init__(
            message="You do not have permission to access this application.",
            error_type="application-access-forbidden",
            status_code=403,
            data=data,
        )


class InvalidStatusTransitionError(AppError):
    def __init__(self, *, current_status: str, valid_next_statuses: list[str]) -> None:
        super().__init__(
            message=f"Cannot transition from '{current_status}' to the requested status.",
            error_type="invalid-status-transition",
            status_code=422,
            data={
                "currentStatus": current_status,
                "validNextStatuses": valid_next_statuses,
            },
        )


class DocumentNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Document not found.",
            error_type="document-not-found",
            status_code=404,
        )


class DocumentTypeNotAllowedError(AppError):
    def __init__(self, *, detected_type: str, allowed_types: list[str]) -> None:
        super().__init__(
            message="The uploaded file type is not allowed for this document requirement.",
            error_type="document-type-not-allowed",
            status_code=422,
            data={"detectedType": detected_type, "allowedTypes": allowed_types},
        )


class FileTooLargeError(AppError):
    def __init__(self, *, max_bytes: int) -> None:
        super().__init__(
            message="The uploaded file exceeds the maximum allowed size.",
            error_type="file-too-large",
            status_code=413,
            data={"maxBytes": max_bytes},
        )


class DocumentAccessForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="You do not have permission to access this document.",
            error_type="document-access-forbidden",
            status_code=403,
        )


class AgentNotAvailableError(AppError):
    def __init__(self, *, reason: str = "Agent is not available for new cases.") -> None:
        super().__init__(
            message=reason,
            error_type="agent-not-available",
            status_code=409,
        )


class ApplicationAlreadyAssignedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="This application has already been assigned to an agent.",
            error_type="application-already-assigned",
            status_code=409,
        )


class DailyCapExceededError(AppError):
    def __init__(self, *, cap: int) -> None:
        super().__init__(
            message="The agent has reached their daily case cap.",
            error_type="daily-cap-exceeded",
            status_code=409,
            data={"cap": cap},
        )


class MessageNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Message not found.",
            error_type="message-not-found",
            status_code=404,
        )


class ValidationError(AppError):
    def __init__(self, *, message: str, fields: list[str] | None = None) -> None:
        super().__init__(
            message=message,
            error_type="validation-error",
            status_code=422,
            data={"fields": fields or []},
        )


class AgentSkillNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent skill profile not found.",
            error_type="agent-skill-not-found",
            status_code=404,
        )


class InvalidServiceCategoryError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Invalid service category.",
            error_type="invalid-service-category",
            status_code=422,
        )


class PaymentNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Payment not found.",
            error_type="payment-not-found",
            status_code=404,
        )


class PaymentAlreadyPaidError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="This application has already been paid.",
            error_type="payment-already-paid",
            status_code=409,
        )


class PaymentExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="The payment window has expired.",
            error_type="payment-expired",
            status_code=410,
        )


class PaymentGatewayError(AppError):
    def __init__(self, *, message: str = "Payment gateway error.") -> None:
        super().__init__(
            message=message,
            error_type="payment-gateway-error",
            status_code=502,
        )
