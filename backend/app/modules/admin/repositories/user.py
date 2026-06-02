from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.admin.models.associations import user_role
from app.modules.admin.models.role import Role
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

    async def list_active_by_role(self, db: AsyncSession, role_name: str) -> list[User]:
        """Usuarios activos (no borrados) que tienen el rol `role_name`, ordenados por
        nombre. Helper aditivo usado por crm (`GET /advisors/active`) — el rol ASESOR
        tiene LEAD_ASSIGNMENTS_READ pero no USERS_VIEW, así que crm no puede ir a
        /admin/users (mismo criterio aditivo que `branch_repository.get_by_ids`)."""
        result = await db.execute(
            select(User)
            .join(user_role, user_role.c.user_id == User.id)
            .join(Role, Role.id == user_role.c.role_id)
            .where(
                Role.name == role_name,
                User.active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.first_name.asc(), User.last_name.asc())
        )
        return list(result.scalars().all())

    async def has_role(self, db: AsyncSession, user_id: str, role_name: str) -> bool:
        """True si el usuario tiene el rol `role_name`. Usado por crm para validar
        que un advisor sea ASESOR (ADVISOR_NOT_ASESOR)."""
        result = await db.execute(
            select(User.id)
            .join(user_role, user_role.c.user_id == User.id)
            .join(Role, Role.id == user_role.c.role_id)
            .where(User.id == user_id, Role.name == role_name)
            .limit(1)
        )
        return result.scalars().first() is not None


user_repository = UserRepository()
