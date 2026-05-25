"""HTTP routes for the authentication module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.core.api import ApiResponse, success_response
from app.core.exceptions import UnauthorizedError
from app.core.ratelimit import rate_limit
from app.modules.auth.dependencies import (
    get_access_payload_optional,
    get_auth_service,
    get_refresh_token,
    require_access_payload,
)
from app.modules.auth.schemas import (
    AuthFlowData,
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
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/signup",
    response_model=ApiResponse[AuthFlowData],
    dependencies=[Depends(rate_limit("auth-signup", 10, 60))],
)
async def signup(
    payload: SignupRequest,
    response: Response,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[AuthFlowData]:
    result = await service.signup(payload, ip_address=_client_ip(request))
    if result.token_bundle is not None:
        service.token_service.apply_session_cookies(response, result.token_bundle)
    return success_response(message="Account created. Verification required.", data=result.payload)


@router.post(
    "/login",
    response_model=ApiResponse[AuthFlowData],
    dependencies=[Depends(rate_limit("auth-login", 10, 60))],
)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[AuthFlowData]:
    result = await service.login(payload, ip_address=_client_ip(request))
    if result.token_bundle is not None:
        service.token_service.apply_session_cookies(response, result.token_bundle)
    return success_response(message="Login accepted. Verification required.", data=result.payload)


@router.post(
    "/verify-otp",
    response_model=ApiResponse[VerifyOtpData],
    dependencies=[Depends(rate_limit("auth-verify-otp", 12, 60))],
)
async def verify_otp(
    payload: VerifyOtpRequest,
    access_payload: dict[str, Any] = Depends(require_access_payload),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[VerifyOtpData]:
    result = await service.verify_client_otp(payload, current_user_id=access_payload["sub"])
    return success_response(message="Verification completed.", data=result.payload)


@router.post("/resend-otp", response_model=ApiResponse[VerifyOtpData])
async def resend_otp(
    access_payload: dict[str, Any] = Depends(require_access_payload),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[VerifyOtpData]:
    result = await service.resend_client_otp(current_user_id=access_payload["sub"])
    return success_response(message="A new verification code has been issued.", data=result.payload)


@router.post(
    "/forgot-password",
    response_model=ApiResponse[ForgotPasswordData],
    dependencies=[Depends(rate_limit("auth-forgot-password", 5, 60))],
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[ForgotPasswordData]:
    result = await service.forgot_password(payload)
    return success_response(message="Password reset instructions queued.", data=result.payload)


@router.post("/reset-password", response_model=ApiResponse[VerifyOtpData])
async def reset_password(
    payload: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[VerifyOtpData]:
    result = await service.reset_password(payload)
    return success_response(message="Password updated successfully.", data=result.payload)


@router.post("/sign-out", response_model=ApiResponse[SignOutData])
async def sign_out(
    response: Response,
    refresh_token: str | None = Depends(get_refresh_token),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[SignOutData]:
    result = await service.sign_out(refresh_token=refresh_token)
    service.token_service.clear_session_cookies(response)
    return success_response(message="Signed out successfully.", data=result.payload)


@router.post(
    "/staff/login",
    response_model=ApiResponse[StaffLoginData],
    dependencies=[Depends(rate_limit("auth-staff-login", 10, 60))],
)
async def staff_login(
    payload: StaffLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[StaffLoginData]:
    result = await service.staff_login(payload, ip_address=_client_ip(request))
    return success_response(message="Primary staff authentication completed.", data=result.payload)


@router.post(
    "/staff/2fa",
    response_model=ApiResponse[SessionData],
    dependencies=[Depends(rate_limit("auth-staff-2fa", 12, 60))],
)
async def staff_two_factor(
    payload: StaffTwoFactorRequest,
    response: Response,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[SessionData]:
    result = await service.staff_two_factor(
        payload,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if result.token_bundle is not None:
        service.token_service.apply_session_cookies(response, result.token_bundle)
    return success_response(message="Staff session established.", data=result.payload)


@router.get("/session", response_model=ApiResponse[SessionData])
async def get_session(
    response: Response,
    access_payload: dict[str, Any] | None = Depends(get_access_payload_optional),
    refresh_token: str | None = Depends(get_refresh_token),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[SessionData]:
    if access_payload is not None:
        expires_at = None
        if "exp" in access_payload:
            expires_at = datetime.fromtimestamp(access_payload["exp"], tz=UTC)
        if (
            refresh_token is not None
            and expires_at is not None
            and (expires_at - datetime.now(UTC)).total_seconds() <= 300
        ):
            result = await service.refresh_session(refresh_token=refresh_token)
            if result.token_bundle is not None:
                service.token_service.apply_session_cookies(response, result.token_bundle)
            return success_response(message="Session refreshed.", data=result.payload)
        result = await service.get_session(current_user_id=access_payload["sub"], expires_at=expires_at)
        return success_response(message="Session is valid.", data=result.payload)
    if refresh_token is None:
        raise UnauthorizedError()
    result = await service.refresh_session(refresh_token=refresh_token)
    if result.token_bundle is not None:
        service.token_service.apply_session_cookies(response, result.token_bundle)
    return success_response(message="Session refreshed.", data=result.payload)


@router.delete("/session", response_model=ApiResponse[SignOutData])
async def delete_session(
    response: Response,
    refresh_token: str | None = Depends(get_refresh_token),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[SignOutData]:
    result = await service.sign_out(refresh_token=refresh_token)
    service.token_service.clear_session_cookies(response)
    return success_response(message="Session closed.", data=result.payload)
