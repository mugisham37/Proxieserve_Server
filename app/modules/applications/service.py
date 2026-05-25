"""Applications module public service surface."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.exceptions import ClaimNotFoundError

PRX_PATTERN = re.compile(r"^PRX-\d{4}-\d{5}$")


@dataclass(slots=True)
class ApplicationLookupResult:
    code: str
    serviceName: str
    submittedDate: str
    status: str


class ApplicationsService:
    """Public applications seam used by auth and the claim flow."""

    _fixtures = {
        "PRX-2026-00483": ApplicationLookupResult(
            code="PRX-2026-00483",
            serviceName="Passport renewal",
            submittedDate="2026-05-03T09:00:00+00:00",
            status="In progress",
        )
    }

    async def lookup_by_code(self, code: str) -> ApplicationLookupResult:
        self._validate_code(code)
        result = self._fixtures.get(code)
        if result is None:
            raise ClaimNotFoundError()
        return result

    async def claim(self, *, code: str, phone: str) -> None:
        self._validate_code(code)
        if code not in self._fixtures:
            raise ClaimNotFoundError()

    @staticmethod
    def _validate_code(code: str) -> None:
        if not PRX_PATTERN.match(code):
            raise ClaimNotFoundError()
