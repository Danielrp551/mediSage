"""
Generic helpers used across modules.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import UTC, datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Timezone-aware UTC datetime. Stored via `timestamptz` in Postgres."""
    return datetime.now(UTC)


def generate_password(length: int = 14) -> str:
    """Random password with at least one of each: lower, upper, digit, symbol."""
    if length < 8:
        raise ValueError("Password length must be >= 8")
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*()-_"]
    chars = [secrets.choice(p) for p in pools]
    alphabet = "".join(pools)
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
