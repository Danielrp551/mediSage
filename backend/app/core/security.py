"""
Password hashing + JWT generation/decoding.

Access tokens carry `roles` and `permissions` claims so endpoints can
enforce RBAC without a DB lookup per request. Refresh tokens carry a
`family` claim (one login session) and a unique `jti` per token. The
service layer tracks the current `jti` per family in `TokenFamily`,
which lets it both revoke a session atomically and detect refresh-token
reuse (mismatching `jti` → entire family revoked).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Passwords ──────────────────────────────────────


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT tokens ─────────────────────────────────────


def create_access_token(
    subject: str,
    *,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Short-lived bearer token with embedded RBAC claims."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "jti": str(uuid.uuid4()),  # id único por token (auditoría + evita tokens idénticos en el mismo segundo)
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "roles": roles or [],
        "permissions": permissions or [],
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    subject: str,
    *,
    family_id: str | None = None,
) -> tuple[str, str, str]:
    """Long-lived rotation token. Returns `(token, family_id, jti)`.

    Each refresh token carries a unique `jti`. The service layer persists the
    *current* `jti` per family and rejects (revoking the family) any refresh
    that presents a `jti` that doesn't match — that's how token reuse after
    rotation is detected.
    """
    now = datetime.now(UTC)
    family = family_id or str(uuid.uuid4())
    jti = str(uuid.uuid4())
    payload = {
        "sub": subject,
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "family": family,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, family, jti


def decode_token(token: str) -> dict[str, Any]:
    """Validate signature, expiration, `iss`, and `aud`. Caller checks `type`."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )
