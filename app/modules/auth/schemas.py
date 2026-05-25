"""Pydantic DTOs for authentication endpoints."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

AuthRole = Literal["client", "staff:agent", "staff:admin"]
AuthLanguage = Literal["en", "rw", "fr"]
IdentifierType = Literal["email", "phone"]
StaffRoleInput = Literal["agent", "admin"]
TwoFAMethod = Literal["totp", "sms", "backup"]


class LoginRequest(BaseModel):
    identifierType: IdentifierType
    identifier: str = Field(min_length=1)
    password: str = Field(min_length=1)
    rememberMe: bool = True


class SignupRequest(BaseModel):
    name: str = Field(min_length=2)
    identifierType: IdentifierType
    identifier: str = Field(min_length=1)
    password: str = Field(min_length=8)
    language: AuthLanguage
    code: str | None = None
    terms: bool

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value in {None, ""}:
            return None
        assert value is not None
        if not re.match(r"^PRX-\d{4}-\d{5}$", value):
            raise ValueError("Invalid PRX tracking code")
        return value

    @field_validator("terms")
    @classmethod
    def validate_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Terms must be accepted")
        return value


class VerifyOtpRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 6:
            raise ValueError("OTP code must be exactly 6 digits")
        return value


class ForgotPasswordRequest(BaseModel):
    identifierType: IdentifierType
    identifier: str = Field(min_length=1)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8)
    confirmPassword: str = Field(min_length=8)

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.password != self.confirmPassword:
            raise ValueError("Passwords do not match")
        return self


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    role: StaffRoleInput


class StaffTwoFactorRequest(BaseModel):
    code: str = Field(min_length=1)
    method: TwoFAMethod
    trustDevice: bool = False
    pre2faToken: str = Field(min_length=1)


class AuthSessionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    userId: str
    name: str
    email: str
    phone: str | None = None
    role: AuthRole
    isEmailVerified: bool
    language: AuthLanguage
    createdAt: str
    expiresAt: str | None = None


class AuthFlowData(BaseModel):
    session: AuthSessionModel
    maskedEmail: str


class SessionData(BaseModel):
    session: AuthSessionModel


class VerifyOtpData(BaseModel):
    verified: bool = True


class ForgotPasswordData(BaseModel):
    maskedEmail: str


class StaffLoginData(BaseModel):
    session: AuthSessionModel
    pre2faToken: str


class SignOutData(BaseModel):
    signedOut: bool = True
