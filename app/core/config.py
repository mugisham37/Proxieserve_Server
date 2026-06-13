"""Application settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="ProxiServe Server", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    app_cors_origins: list[str] = Field(default_factory=list, alias="APP_CORS_ORIGINS")
    app_trusted_proxy_headers: bool = Field(default=False, alias="APP_TRUSTED_PROXY_HEADERS")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="proxiserve", alias="POSTGRES_DB")
    postgres_user: str = Field(default="proxiserve", alias="POSTGRES_USER")
    postgres_password: str = Field(default="proxiserve", alias="POSTGRES_PASSWORD")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_issuer: str = Field(alias="JWT_ISSUER")
    jwt_audience: str = Field(alias="JWT_AUDIENCE")
    jwt_access_secret: str = Field(alias="JWT_ACCESS_SECRET")
    jwt_refresh_secret: str = Field(alias="JWT_REFRESH_SECRET")
    jwt_pre_2fa_secret: str = Field(alias="JWT_PRE_2FA_SECRET")
    fernet_secret: str = Field(alias="FERNET_SECRET")
    jwt_access_ttl_seconds: int = Field(default=900, alias="JWT_ACCESS_TTL_SECONDS")
    jwt_refresh_ttl_seconds: int = Field(default=86400, alias="JWT_REFRESH_TTL_SECONDS")
    jwt_staff_refresh_ttl_seconds: int = Field(default=28800, alias="JWT_STAFF_REFRESH_TTL_SECONDS")
    jwt_pre_2fa_ttl_seconds: int = Field(default=600, alias="JWT_PRE_2FA_TTL_SECONDS")

    otp_ttl_seconds: int = Field(default=300, alias="OTP_TTL_SECONDS")
    otp_max_attempts: int = Field(default=3, alias="OTP_MAX_ATTEMPTS")
    otp_resend_cooldown_seconds: int = Field(default=30, alias="OTP_RESEND_COOLDOWN_SECONDS")
    lockout_max_attempts: int = Field(default=5, alias="LOCKOUT_MAX_ATTEMPTS")
    lockout_window_seconds: int = Field(default=900, alias="LOCKOUT_WINDOW_SECONDS")
    trusted_device_ttl_seconds: int = Field(default=604800, alias="TRUSTED_DEVICE_TTL_SECONDS")
    password_reset_ttl_seconds: int = Field(default=3600, alias="PASSWORD_RESET_TTL_SECONDS")

    cookie_domain: str | None = Field(default=None, alias="COOKIE_DOMAIN")
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")
    cookie_samesite: str = Field(default="lax", alias="COOKIE_SAMESITE")

    email_from: str = Field(default="noreply@proxiserve.rw", alias="EMAIL_FROM")
    smtp_host: str = Field(default="localhost", alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    sms_provider: str = Field(default="stub", alias="SMS_PROVIDER")

    metrics_path: str = "/metrics"
    health_path: str = "/health"
    ready_path: str = "/ready"

    otel_endpoint: str | None = Field(default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    @field_validator("app_cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            # Support JSON-array syntax: APP_CORS_ORIGINS=["http://localhost:3000"]
            if stripped.startswith("["):
                import json as _json

                try:
                    return [str(item) for item in _json.loads(stripped)]
                except Exception:
                    pass
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @field_validator("cookie_samesite")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of lax, strict, or none")
        return normalized

    @property
    def database_url(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
