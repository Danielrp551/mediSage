from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.admin.models.user import User
from app.shared.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    ALLOWED_FIELDS = {
        "email",
        "first_name",
        "last_name",
        "second_last_name",
        "document_number",
        "document_type",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(User)

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        result = await db.execute(
            select(User)
            .where(User.email == email, User.deleted_at.is_(None))
            .options(selectinload(User.roles), selectinload(User.permissions))
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, user_id: str) -> User | None:
        """`get_by_id` with roles + permissions eagerly loaded for detail views."""
        return await self.get_by_id(
            db,
            user_id,
            load=(selectinload(User.roles), selectinload(User.permissions)),
        )

    async def get_audit_info_map(self, db: AsyncSession, user_ids: set[str]) -> dict[str, User]:
        """Batch-resolve actor IDs to User rows for `created_by`/`updated_by`.

        Used by every entity service to hydrate audit columns into a
        human-readable name. Does NOT filter on `deleted_at` — we want to
        keep the audit trail honest even when the actor was later soft-
        deleted. Hard-deleted (purged) actors return `None` via the dict
        lookup at the service layer.
        """
        if not user_ids:
            return {}
        result = await db.execute(select(User).where(User.id.in_(user_ids)))
        return {u.id: u for u in result.scalars().all()}


user_repository = UserRepository()
