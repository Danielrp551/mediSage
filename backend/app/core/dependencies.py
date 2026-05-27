"""
Reusable FastAPI dependencies and `Annotated` type aliases.

Routers should depend on these instead of `Depends(get_auth)` directly.

Examples:

    async def me(auth: CurrentAuth) -> AuthenticatedUser:
        return _serialize(auth.user)

    @router.post("/", dependencies=[Depends(RequirePermission("USERS_CREATE"))])
    async def create_user(actor: CurrentAuth, ...) -> ...:
        return await service.create(..., actor_id=actor.id)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token
from app.modules.admin.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


DBSession = Annotated[AsyncSession, Depends(get_db)]
"""Per-request async session."""


@dataclass(frozen=True, slots=True)
class AuthContext:
    """
    Authenticated caller. Bundles:
      • `user`: the freshly-loaded ORM entity, for code that needs profile
        fields or wants the *current* roles/permissions from DB.
      • `permissions` / `roles`: codes extracted from the access token —
        used by `RequirePermission` for O(1) RBAC without a DB lookup.

    These can drift if an admin revokes a permission while the token is
    still valid; the next refresh (≤ 15 min by default) re-syncs.
    """

    user: User
    permissions: frozenset[str]
    roles: frozenset[str]

    @property
    def id(self) -> str:
        return self.user.id

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


async def get_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DBSession,
) -> AuthContext:
    """Decode the Bearer access token, load the active user, return the context."""
    if credentials is None:
        raise UnauthorizedException("Missing bearer token")

    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise UnauthorizedException("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise UnauthorizedException("Wrong token type")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("Invalid token payload")

    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .options(selectinload(User.roles), selectinload(User.permissions))
    )
    user = result.scalars().first()
    if user is None or not user.active:
        raise UnauthorizedException("User no longer active")

    return AuthContext(
        user=user,
        permissions=frozenset(payload.get("permissions", [])),
        roles=frozenset(payload.get("roles", [])),
    )


CurrentAuth = Annotated[AuthContext, Depends(get_auth)]


def RequirePermission(*codes: str):
    """
    Dependency factory: enforce that the caller's token carries ALL of `codes`.

    Usage on a router:
        @router.post(
            "/users",
            dependencies=[Depends(RequirePermission("USERS_CREATE"))],
        )
    """
    required = frozenset(codes)

    async def _check(auth: CurrentAuth) -> AuthContext:
        if not required.issubset(auth.permissions):
            missing = sorted(required - auth.permissions)
            raise ForbiddenException(
                f"Missing required permission(s): {', '.join(missing)}",
                code="PERMISSION_DENIED",
            )
        return auth

    return _check
