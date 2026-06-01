"""
PersonContactIdentifier repository. Encapsula las queries del CRUD anidado bajo
`/persons/{id}/identifiers`: listar los vivos de una persona, resolver uno con
ownership (id + person_id) y desmarcar el `is_primary` previo del mismo canal
cuando se marca uno nuevo. La dedup global (channel_type, identifier) la resuelve
`person_repository.get_by_identifier`. `ALLOWED_FIELDS` vacío: no se lista
directamente vía `QueryRequest`, sino por person_id.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.shared.base_repository import BaseRepository


class ContactIdentifierRepository(BaseRepository[PersonContactIdentifier]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(PersonContactIdentifier)

    async def list_for_person(
        self, db: AsyncSession, person_id: str
    ) -> list[PersonContactIdentifier]:
        """Identificadores vivos de una persona, más recientes primero."""
        result = await db.execute(
            select(PersonContactIdentifier)
            .where(
                PersonContactIdentifier.person_id == person_id,
                PersonContactIdentifier.deleted_at.is_(None),
            )
            .order_by(PersonContactIdentifier.created_on.desc())
        )
        return list(result.scalars().all())

    async def get_for_person(
        self, db: AsyncSession, person_id: str, identifier_id: str
    ) -> PersonContactIdentifier | None:
        """Resuelve un identifier vivo CHEQUEANDO ownership (debe pertenecer a esa
        persona). Devuelve None si no existe o es de otra persona (→ 404)."""
        result = await db.execute(
            select(PersonContactIdentifier).where(
                PersonContactIdentifier.id == identifier_id,
                PersonContactIdentifier.person_id == person_id,
                PersonContactIdentifier.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def unmark_primary(
        self,
        db: AsyncSession,
        person_id: str,
        channel_type: str,
        *,
        exclude_id: str | None = None,
        actor_id: str,
        now: datetime,
    ) -> None:
        """Desmarca el is_primary anterior del mismo (person_id, channel_type) en la
        misma tx (al marcar uno nuevo como principal). `exclude_id` evita
        desmarcarse a sí mismo."""
        stmt = (
            update(PersonContactIdentifier)
            .where(
                PersonContactIdentifier.person_id == person_id,
                PersonContactIdentifier.channel_type == channel_type,
                PersonContactIdentifier.is_primary.is_(True),
                PersonContactIdentifier.deleted_at.is_(None),
            )
            .values(is_primary=False, updated_by=actor_id, updated_on=now)
        )
        if exclude_id is not None:
            stmt = stmt.where(PersonContactIdentifier.id != exclude_id)
        await db.execute(stmt)


contact_identifier_repository = ContactIdentifierRepository()
