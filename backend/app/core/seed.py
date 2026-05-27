"""
Idempotent seed: creates the bootstrap admin user, role, and the menu
permissions that the frontend ships with.

Run with: ``python -m app.core.seed`` (Dockerfile invokes it on container start).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.modules.admin.models.permission import Permission
from app.modules.admin.models.role import Role
from app.modules.admin.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()


# Bootstrap permissions — keep in sync with the frontend's `NAV_ITEMS`.
SEED_PERMISSIONS: list[dict[str, str]] = [
    {"code": "MENU-HOME", "name": "Menu Home", "module": "GENERAL"},
    {"code": "MENU-ADMIN-USERS", "name": "Menu Admin Users", "module": "ADMIN"},
    {"code": "MENU-ADMIN-ROLES", "name": "Menu Admin Roles", "module": "ADMIN"},
    {"code": "MENU-ADMIN-PERMISSIONS", "name": "Menu Admin Permissions", "module": "ADMIN"},
    {"code": "USERS_VIEW", "name": "View users", "module": "ADMIN"},
    {"code": "USERS_CREATE", "name": "Create users", "module": "ADMIN"},
    {"code": "USERS_UPDATE", "name": "Update users", "module": "ADMIN"},
    {"code": "ROLES_VIEW", "name": "View roles", "module": "ADMIN"},
    {"code": "ROLES_CREATE", "name": "Create roles", "module": "ADMIN"},
    {"code": "ROLES_UPDATE", "name": "Update roles", "module": "ADMIN"},
    {"code": "PERMISSIONS_VIEW", "name": "View permissions", "module": "ADMIN"},
    {"code": "PERMISSIONS_CREATE", "name": "Create permissions", "module": "ADMIN"},
    {"code": "PERMISSIONS_UPDATE", "name": "Update permissions", "module": "ADMIN"},
]


async def _seed_permissions(db: AsyncSession, actor_id: str) -> list[Permission]:
    existing = (await db.execute(select(Permission))).scalars().all()
    by_code = {p.code: p for p in existing}
    out: list[Permission] = []
    now = datetime.now(timezone.utc)
    for spec in SEED_PERMISSIONS:
        if spec["code"] in by_code:
            out.append(by_code[spec["code"]])
            continue
        perm = Permission(
            id=str(uuid.uuid4()),
            code=spec["code"],
            name=spec["name"],
            description=spec["name"],
            module=spec["module"],
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
        db.add(perm)
        out.append(perm)
        logger.info("seed.permission.created code=%s", spec["code"])
    return out


async def _seed_admin_role(
    db: AsyncSession, actor_id: str, permissions: list[Permission]
) -> Role:
    existing = (
        await db.execute(select(Role).where(Role.name == "ADMIN"))
    ).scalars().first()
    if existing is not None:
        existing.permissions = permissions
        return existing
    now = datetime.now(timezone.utc)
    role = Role(
        id=str(uuid.uuid4()),
        name="ADMIN",
        description="Full administrative access",
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        permissions=permissions,
    )
    db.add(role)
    logger.info("seed.role.created name=ADMIN")
    return role


async def _seed_admin_user(db: AsyncSession, role: Role, actor_id: str) -> User:
    existing = (
        await db.execute(select(User).where(User.email == settings.SEED_ADMIN_EMAIL))
    ).scalars().first()
    if existing is not None:
        existing.roles = [role]
        return existing
    now = datetime.now(timezone.utc)
    user = User(
        id=actor_id,
        email=settings.SEED_ADMIN_EMAIL,
        password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
        first_name="Admin",
        last_name="User",
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        roles=[role],
    )
    db.add(user)
    logger.info("seed.user.created email=%s", settings.SEED_ADMIN_EMAIL)
    return user


async def seed() -> None:
    """Run the full seed inside one transaction."""
    actor_id = "00000000-0000-0000-0000-000000000001"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            perms = await _seed_permissions(db, actor_id)
            await db.flush()
            role = await _seed_admin_role(db, actor_id, perms)
            await db.flush()
            await _seed_admin_user(db, role, actor_id)


if __name__ == "__main__":
    configure_logging(settings.LOG_LEVEL)
    asyncio.run(seed())
