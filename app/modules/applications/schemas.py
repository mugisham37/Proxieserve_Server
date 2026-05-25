"""DTOs for the applications stub seam."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class ApplicationLookupData(BaseModel):
    code: str
    serviceName: str
    submittedDate: str
    status: str


class ApplicationClaimRequest(BaseModel):
    code: str = Field(min_length=14, max_length=14)
    phone: str = Field(min_length=9)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.match(r"^PRX-\d{4}-\d{5}$", value):
            raise ValueError("Invalid PRX code")
        return value


class ApplicationClaimData(BaseModel):
    claimed: bool = True
