"""
Person repository. `ALLOWED_FIELDS` whitelist las columnas reales de `person`
que el frontend puede filtrar/ordenar dinámicamente vía `QueryRequest`.
`full_name`/`primary_identifier`/`lead_status`/`customer_status`/
`assigned_advisor`/`last_activity_at` son DENORMALIZADOS → NO están aquí
(lección cd10c78: filtrar/ordenar por ellos daría 400). Soft-delete lo maneja
`BaseRepository` (todo read filtra `deleted_at IS NULL`).

⚠ F1 subset: `get_full` carga SOLO `identifiers` (filtrando soft-deleted vía
`with_loader_criteria`). Las relaciones lead_status/customer_status/assignment
NO existen en F1 — se agregan a este eager-load en F3/F4 cuando sus modelos
existan. `get_by_identifier`/`search`/`list_active` solo tocan person +
identifier.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.shared.base_repository import BaseRepository


class PersonRepository(BaseRepository[Person]):
    # ONLY real columns of `person`. Default sort = created_on desc (handled by
    # the QueryRequest sorting; sin sorting el orden lo decide el caller).
    ALLOWED_FIELDS: set[str] = {
        "first_name",
        "last_name",
        "second_last_name",
        "document_type",
        "document_number",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Person)

    async def get_by_identifier(
        self, db: AsyncSession, channel_type: str, identifier: str
    ) -> Person | None:
        """Resolve the Person owning a live (channel_type, identifier). Powers
        /persons/search and find_by_identifier_or_create (the bot path)."""
        result = await db.execute(
            select(Person)
            .join(PersonContactIdentifier, PersonContactIdentifier.person_id == Person.id)
            .where(
                PersonContactIdentifier.channel_type == channel_type,
                PersonContactIdentifier.identifier == identifier,
                PersonContactIdentifier.deleted_at.is_(None),
                Person.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, person_id: str) -> Person | None:
        """Eager-load identifiers (live). with_loader_criteria filters soft-deleted
        children at load time. F1: solo identifiers (lead/customer/assignment en
        F3/F4)."""
        return await self.get_by_id(
            db,
            person_id,
            load=(
                selectinload(Person.identifiers),
                with_loader_criteria(
                    PersonContactIdentifier,
                    PersonContactIdentifier.deleted_at.is_(None),
                    include_aliases=True,
                ),
            ),
        )

    async def search(
        self,
        db: AsyncSession,
        q: str | None = None,
        channel_type: str | None = None,
        identifier: str | None = None,
        limit: int = 20,
    ) -> list[Person]:
        """Functional search for the bot (/persons/search). Exact identifier match
        when (channel_type, identifier) given; else ILIKE on name/document."""
        if channel_type is not None and identifier is not None:
            person = await self.get_by_identifier(db, channel_type, identifier)
            return [person] if person is not None else []
        stmt = select(Person).where(Person.deleted_at.is_(None)).limit(limit)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Person.first_name.ilike(like),
                    Person.last_name.ilike(like),
                    Person.document_number.ilike(like),
                )
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self, db: AsyncSession) -> list[Person]:
        result = await db.execute(
            select(Person)
            .where(Person.active.is_(True), Person.deleted_at.is_(None))
            .order_by(Person.created_on.desc())
        )
        return list(result.scalars().all())

    async def primary_identifier_map(
        self, db: AsyncSession, person_ids: list[str]
    ) -> dict[str, PersonContactIdentifier]:
        """Batch del identifier principal por persona — una query, sin N+1. Alimenta
        PersonItem.primary_identifier. Prefiere el `is_primary` vivo; si una persona
        tiene varios canales con principal, gana el más reciente (created_on desc).
        Las personas sin identifier principal quedan fuera del map (→ None)."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(PersonContactIdentifier)
            .where(
                PersonContactIdentifier.person_id.in_(person_ids),
                PersonContactIdentifier.is_primary.is_(True),
                PersonContactIdentifier.deleted_at.is_(None),
            )
            .order_by(PersonContactIdentifier.created_on.desc())
        )
        out: dict[str, PersonContactIdentifier] = {}
        for ident in result.scalars().all():
            # El primero por persona gana (created_on desc → el más reciente).
            out.setdefault(ident.person_id, ident)
        return out


person_repository = PersonRepository()
