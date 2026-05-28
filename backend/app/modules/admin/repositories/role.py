from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.admin.models.role import Role
from app.shared.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    ALLOWED_FIELDS = {"name", "description", "active", "created_on", "updated_on"}

    def __init__(self) -> None:
        super().__init__(Role)

    async def list_active(self, db: AsyncSession) -> list[Role]:
        q = select(Role).where(Role.active.is_(True), Role.deleted_at.is_(None)).order_by(Role.name)
        return list((await db.execute(q)).scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Role]:
        if not ids:
            return []
        q = (
            select(Role)
            .where(Role.id.in_(ids), Role.deleted_at.is_(None))
            .options(selectinload(Role.permissions))
        )
        return list((await db.execute(q)).scalars().all())

    async def get_by_name(self, db: AsyncSession, name: str) -> Role | None:
        q = select(Role).where(Role.name == name, Role.deleted_at.is_(None))
        return (await db.execute(q)).scalars().first()


role_repository = RoleRepository()
