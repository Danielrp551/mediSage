from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models.permission import Permission
from app.shared.base_repository import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    ALLOWED_FIELDS = {"code", "name", "description", "module", "active", "created_on", "updated_on"}

    def __init__(self) -> None:
        super().__init__(Permission)

    async def list_active(self, db: AsyncSession) -> list[Permission]:
        q = (
            select(Permission)
            .where(Permission.active.is_(True), Permission.deleted_at.is_(None))
            .order_by(Permission.module, Permission.name)
        )
        return list((await db.execute(q)).scalars().all())

    async def get_by_code(self, db: AsyncSession, code: str) -> Permission | None:
        q = select(Permission).where(Permission.code == code, Permission.deleted_at.is_(None))
        return (await db.execute(q)).scalars().first()

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Permission]:
        if not ids:
            return []
        q = select(Permission).where(Permission.id.in_(ids), Permission.deleted_at.is_(None))
        return list((await db.execute(q)).scalars().all())


permission_repository = PermissionRepository()
