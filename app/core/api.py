"""Shared API response models and helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    """Uniform response envelope used across the API."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    errorType: str | None = None
    message: str
    data: DataT | None = None


def success_response(*, message: str, data: DataT | None = None) -> ApiResponse[DataT]:
    return ApiResponse(success=True, errorType=None, message=message, data=data)


def error_response(*, message: str, error_type: str, data: DataT | None = None) -> ApiResponse[DataT]:
    return ApiResponse(success=False, errorType=error_type, message=message, data=data)
