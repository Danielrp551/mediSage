"""
Person repository. `ALLOWED_FIELDS` whitelist las columnas reales de `person`
que el frontend puede filtrar/ordenar dinámicamente vía `QueryRequest`.
`full_name`/`primary_identifier`/`lead_status`/`customer_status`/
`assigned_advisor`/`last_activity_at` son DENORMALIZADOS → NO están aquí
(lección cd10c78: filtrar/ordenar por ellos daría 400). Soft-delete lo maneja
`BaseRepository` (todo read filtra `deleted_at IS NULL`).

⚠ F1 subset: `get_full` carga SOLO `identifiers` (filtrando soft-deleted vía
`with_loader_criteria`). Los estados lead/customer/assignment NO se cargan por
relationship (Person quedó intacto, sin rel a los hijos de lifecycle): se
denormalizan vía batch maps en el service (status_map). `get_by_identifier`/
`search`/`list_active` solo tocan person + identifier.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.crm.models.lead_assignment import LeadAssignment
from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.crm.models.person_lead_status import PersonLeadStatus
from app.shared.base_repository import BaseRepository
from app.shared.base_schemas import QueryRequest
from app.shared.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sorting,
    build_count_query,
)


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

    async def get_by_ids(self, db: AsyncSession, person_ids: list[str]) -> list[Person]:
        """Batch fetch de personas VIVAS por ids (aditivo, molde `staff.branch_repository.
        get_by_ids`). Lo consume `person_option_map` (denorm de la persona en el inbox de
        conversations) sin N+1."""
        if not person_ids:
            return []
        result = await db.execute(
            select(Person).where(Person.id.in_(person_ids), Person.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def list_paginated_filtered(
        self,
        db: AsyncSession,
        query_request: QueryRequest,
        *,
        lead_status_id: str | None = None,
        customer_status_id: str | None = None,
        advisor_user_id: str | None = None,
        has_active_lead: bool | None = None,
    ) -> tuple[list[Person], int]:
        """Igual que `BaseRepository.get_paginated` pero traduce los deep-links de
        estado lead/cliente/asesor/"lead activo" a EXISTS correlados sobre
        person_lead_status / person_customer_status / lead_assignment (patrón staff
        `?branch_id=`). Los deep-links NO son columnas de `person` → no van en
        ALLOWED_FIELDS (lección cd10c78)."""
        conditions: list[ColumnElement[bool]] = []
        if lead_status_id is not None:
            conditions.append(
                select(PersonLeadStatus.id)
                .where(
                    PersonLeadStatus.person_id == Person.id,
                    PersonLeadStatus.lead_status_id == lead_status_id,
                    PersonLeadStatus.deleted_at.is_(None),
                )
                .exists()
            )
        if customer_status_id is not None:
            conditions.append(
                select(PersonCustomerStatus.id)
                .where(
                    PersonCustomerStatus.person_id == Person.id,
                    PersonCustomerStatus.customer_status_id == customer_status_id,
                    PersonCustomerStatus.deleted_at.is_(None),
                )
                .exists()
            )
        if advisor_user_id is not None:
            conditions.append(
                select(LeadAssignment.id)
                .where(
                    LeadAssignment.person_id == Person.id,
                    LeadAssignment.advisor_user_id == advisor_user_id,
                    LeadAssignment.deleted_at.is_(None),
                )
                .exists()
            )
        if has_active_lead is not None:
            has_lead = (
                select(PersonLeadStatus.id)
                .where(
                    PersonLeadStatus.person_id == Person.id,
                    PersonLeadStatus.deleted_at.is_(None),
                )
                .exists()
            )
            conditions.append(has_lead if has_active_lead else ~has_lead)

        q = select(Person).where(Person.deleted_at.is_(None))
        for cond in conditions:
            q = q.where(cond)
        q = apply_filters(q, Person, query_request.filters, self.ALLOWED_FIELDS)
        q = apply_sorting(q, Person, query_request.sorting, self.ALLOWED_FIELDS)
        q = apply_pagination(q, query_request.pagination)
        items = list((await db.execute(q)).scalars().all())

        count_q = build_count_query(Person, query_request.filters, self.ALLOWED_FIELDS).where(
            Person.deleted_at.is_(None)
        )
        for cond in conditions:
            count_q = count_q.where(cond)
        total = (await db.execute(count_q)).scalar() or 0
        return items, total

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
