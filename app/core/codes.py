"""Application code generation utilities."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


def generate_prx_code() -> str:
    """Generate a human-readable PRX code in PRX-YYYY-NNNNN format."""
    year = datetime.now(UTC).year
    suffix = f"{secrets.randbelow(100_000):05d}"
    return f"PRX-{year}-{suffix}"
