"""
Login, token refresh (with rotation + family revocation + reuse detection), logout.

Rotation contract (also documented in `models/token_family.py`):

  • Login creates a `TokenFamily` row and issues the initial refresh JTI.
  • Every refresh verifies the incoming JTI matches `family.current_jti`.
      – Match  → rotate (issue new JTI, update column, return new pair).
      – Mismatch → token was already rotated (reuse attempt). Revoke the
        family. Any subsequent refresh on it fails.
  • Logout revokes the family explicitly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories import token_family as token_family_repo
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.auth import (
    AuthenticatedUser,
    LoginResponse,
    TokenPair,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _serialize_user(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        first_name=user.first_name,
        last_name=user.last_name,
        second_last_name=user.second_last_name,
        active=user.active,
        roles=sorted(r.name for r in user.roles),
        permissions=user.effective_permission_codes(),
    )


def _issue_tokens(user: User, *, family_id: str | None = None) -> tuple[TokenPair, str, str]:
    """Build a fresh access + refresh pair. Returns `(pair, family_id, jti)`."""
    roles = [r.name for r in user.roles]
    perms = user.effective_permission_codes()
    access = create_access_token(user.id, roles=roles, permissions=perms)
    refresh, family, jti = create_refresh_token(user.id, family_id=family_id)

    now = datetime.now(UTC)
    pair = TokenPair(
        access_token=access,
        refresh_token=refresh,
        access_expires_at=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        refresh_expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return pair, family, jti


# ── Login ─────────────────────────────────────────


async def login(db: AsyncSession, *, email: str, password: str) -> LoginResponse:
    user = await user_repository.get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        # Generic error — don't leak whether the email exists.
        raise UnauthorizedException("Invalid credentials")
    if not user.active:
        raise UnauthorizedException("User is disabled")

    pair, family_id, jti = _issue_tokens(user)
    await token_family_repo.create_family(db, family_id=family_id, user_id=user.id, initial_jti=jti)
    return LoginResponse(tokens=pair, user=_serialize_user(user))


# ── Refresh ───────────────────────────────────────


async def refresh(db: AsyncSession, *, refresh_token: str) -> LoginResponse:
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError as exc:
        raise UnauthorizedException("Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise UnauthorizedException("Wrong token type")

    family_id = payload.get("family")
    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not family_id or not jti or not user_id:
        raise UnauthorizedException("Malformed refresh token")

    # Pessimistic lock — serialises concurrent refreshes on the same family
    # so the reuse check below is race-free. See repo docstring.
    family = await token_family_repo.get_family_for_update(db, family_id)
    if family is None:
        # No row for this family — token from a wiped DB or forged.
        raise UnauthorizedException("Unknown session")

    if family.revoked_at is not None:
        logger.warning(
            "auth.refresh.revoked family_id=%s user_id=%s reason=%s",
            family_id,
            user_id,
            family.reason,
        )
        raise UnauthorizedException("Session revoked, please log in again")

    if family.current_jti != jti:
        # The presented JTI is not the current one → this token was already
        # rotated → either replay or theft. Revoke the entire family.
        await token_family_repo.revoke(db, family, reason="refresh_reuse_detected")
        # La revocación es un efecto de seguridad que DEBE persistir aunque a
        # continuación se aborte con 401. get_db hace rollback ante cualquier
        # excepción, lo que desharía el revoke; por eso se commitea explícitamente
        # aquí (excepción justificada a la regla "los services no commitean").
        await db.commit()
        logger.warning(
            "auth.refresh.reuse_detected family_id=%s user_id=%s presented=%s current=%s",
            family_id,
            user_id,
            jti,
            family.current_jti,
        )
        raise UnauthorizedException("Token reuse detected, session terminated")

    user = await user_repository.get_full(db, user_id)
    if user is None or not user.active:
        await token_family_repo.revoke(db, family, reason="user_inactive")
        await db.commit()  # persistir el revoke pese al 401 (ver nota en el bloque de reuso)
        raise UnauthorizedException("User is no longer active")

    pair, _, new_jti = _issue_tokens(user, family_id=family_id)
    await token_family_repo.rotate_jti(db, family, new_jti)
    return LoginResponse(tokens=pair, user=_serialize_user(user))


# ── Logout ────────────────────────────────────────


async def logout(db: AsyncSession, *, refresh_token: str) -> None:
    """Revoke the refresh-token family. Safe to call with expired tokens."""
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError:
        return  # token already dead; nothing to revoke

    family_id = payload.get("family")
    if not family_id:
        return

    family = await token_family_repo.get_family(db, family_id)
    if family is not None and family.revoked_at is None:
        await token_family_repo.revoke(db, family, reason="logout")
