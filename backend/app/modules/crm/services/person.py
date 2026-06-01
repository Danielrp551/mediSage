"""
Person service. Módulo de funciones (no clases), por convención del template.
Hidrata audit users (`created_by_user`/`updated_by_user`) y denormaliza
`full_name` + `primary_identifier` en cada Item (batch, sin N+1). Los paths de
detalle recargan vía `person_repository.get_full` (identifiers eager,
soft-deleted filtrados); `create`/`update` solo refrescan columnas.

Creación de Person + identifiers nested en UNA transacción, con dedup proactivo
(`get_by_identifier` → 409 IDENTIFIER_TAKEN) y `is_primary` único por canal. NO
crea lead automáticamente.

⚠ F1 subset: lead_status/customer_status/assigned_advisor/last_activity_at de
PersonItem/PersonDetail son SIEMPRE None (no hay tabla fuente hasta F3/F4). Los
query params deep-link (lead_status_id/customer_status_id/advisor_user_id/
has_active_lead) se ACEPTAN en la firma pero son NO-OP en F1.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType
from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.schemas.contact_identifier import ContactIdentifierItem
from app.modules.crm.schemas.person import (
    PersonCreate,
    PersonDetail,
    PersonItem,
    PersonOption,
    PersonPrimaryIdentifier,
    PersonUpdate,
)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now

# Usuario sistema (seed F0). Lo usa find_by_identifier_or_create (F5) como actor
# de las altas automáticas del bot.
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000002"


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _full_name(person: Person) -> str:
    return f"{person.first_name} {person.last_name} {person.second_last_name or ''}".strip()


def _to_item(
    person: Person,
    audit_users: dict[str, User],
    *,
    primary_identifier: PersonContactIdentifier | None = None,
) -> PersonItem:
    return PersonItem(
        id=person.id,
        full_name=_full_name(person),
        first_name=person.first_name,
        last_name=person.last_name,
        second_last_name=person.second_last_name,
        document_type=person.document_type,
        document_number=person.document_number,
        active=person.active,
        primary_identifier=(
            PersonPrimaryIdentifier.model_validate(primary_identifier, from_attributes=True)
            if primary_identifier is not None
            else None
        ),
        # F1: sin tabla fuente — siempre None (se pueblan en F3/F4).
        lead_status=None,
        customer_status=None,
        assigned_advisor=None,
        last_activity_at=None,
        created_on=person.created_on,
        created_by=person.created_by,
        created_by_user=_audit_info(audit_users.get(person.created_by)),
        updated_on=person.updated_on,
        updated_by=person.updated_by,
        updated_by_user=_audit_info(audit_users.get(person.updated_by)),
    )


def _to_detail(person: Person, audit_users: dict[str, User]) -> PersonDetail:
    # `person.identifiers` debe venir eager (get_full) — es `lazy="raise"` y ya
    # filtra soft-deleted por el with_loader_criteria de get_full. El principal de
    # la cabecera se toma de esa misma colección (sin query extra).
    # Orden determinista (created_on desc): la cabecera toma el principal más
    # reciente —mismo desempate que `primary_identifier_map` del listado— y la
    # lista del detalle queda igual que el sub-recurso /identifiers (list_for_person).
    sorted_identifiers = sorted(person.identifiers, key=lambda i: i.created_on, reverse=True)
    primary = next((i for i in sorted_identifiers if i.is_primary), None)
    return PersonDetail(
        **_to_item(person, audit_users, primary_identifier=primary).model_dump(),
        birth_date=person.birth_date,
        gender=person.gender,
        address=person.address,
        notes=person.notes,
        identifiers=[
            ContactIdentifierItem.model_validate(i, from_attributes=True)
            for i in sorted_identifiers
        ],
    )


def _collect_actor_ids(rows: list[Person]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _guard_identifier_unique(
    db: AsyncSession, channel_type: ChannelType, identifier: str
) -> None:
    """409 IDENTIFIER_TAKEN si un identifier vivo (de cualquier persona) ya usa el
    par (channel_type, identifier)."""
    existing = await person_repository.get_by_identifier(db, channel_type.value, identifier)
    if existing is not None:
        raise AlreadyExistsException(
            f"El identificador '{channel_type.value}:{identifier}' ya está registrado",
            code="IDENTIFIER_TAKEN",
        )


async def list_active(db: AsyncSession) -> list[PersonOption]:
    """Lista personas activas para dropdowns. Devuelve la lista cruda (sin
    envelope), consistente con el módulo."""
    rows = await person_repository.list_active(db)
    person_ids = [p.id for p in rows]
    primary_map = await person_repository.primary_identifier_map(db, person_ids)
    return [
        PersonOption(
            id=p.id,
            full_name=_full_name(p),
            document_number=p.document_number,
            primary_identifier=(
                PersonPrimaryIdentifier.model_validate(primary_map[p.id], from_attributes=True)
                if p.id in primary_map
                else None
            ),
        )
        for p in rows
    ]


async def search(
    db: AsyncSession,
    *,
    q: str | None = None,
    channel_type: str | None = None,
    identifier: str | None = None,
) -> SingleResponse[list[PersonOption]]:
    """Búsqueda funcional (la usará el bot). (channel_type, identifier) exacto →
    match único; `q` → ILIKE sobre nombre/documento. Lista vacía si no hay match
    (no 404)."""
    rows = await person_repository.search(db, q=q, channel_type=channel_type, identifier=identifier)
    primary_map = await person_repository.primary_identifier_map(db, [p.id for p in rows])
    options = [
        PersonOption(
            id=p.id,
            full_name=_full_name(p),
            document_number=p.document_number,
            primary_identifier=(
                PersonPrimaryIdentifier.model_validate(primary_map[p.id], from_attributes=True)
                if p.id in primary_map
                else None
            ),
        )
        for p in rows
    ]
    return SingleResponse(data=options)


async def get_by_id(db: AsyncSession, person_id: str) -> SingleResponse[PersonDetail]:
    person = await person_repository.get_full(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(
        db, {person.created_by, person.updated_by}
    )
    return SingleResponse(data=_to_detail(person, audit_users))


async def list_paginated(
    db: AsyncSession,
    query_request: QueryRequest,
    *,
    lead_status_id: str | None = None,
    customer_status_id: str | None = None,
    advisor_user_id: str | None = None,
    has_active_lead: bool | None = None,
) -> PaginatedResponse[PersonItem]:
    # TODO F3/F4: traducir lead_status_id/customer_status_id/advisor_user_id/
    # has_active_lead a EXISTS sub-selects sobre person_lead_status/lead_assignment
    # antes de delegar en get_paginated. En F1 esas tablas no existen → no-op.
    items, total = await person_repository.get_paginated(db, query_request)
    person_ids = [p.id for p in items]
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    primary_map = await person_repository.primary_identifier_map(db, person_ids)
    rows = [_to_item(p, audit_users, primary_identifier=primary_map.get(p.id)) for p in items]
    return PaginatedResponse(
        data=PaginatedData(
            items=rows,
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: PersonCreate, *, actor_id: str
) -> SingleResponse[PersonDetail]:
    # 1) Dedup proactivo de los identifiers inline (contra filas vivas). El
    #    validator Pydantic ya garantizó: sin duplicados internos + ≤1 principal
    #    por canal en el body.
    for ident in payload.identifiers:
        await _guard_identifier_unique(db, ident.channel_type, ident.identifier)

    now = utc_now()
    person = Person(
        id=generate_uuid(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        second_last_name=payload.second_last_name,
        document_type=payload.document_type,
        document_number=payload.document_number,
        birth_date=payload.birth_date,
        gender=payload.gender,
        address=payload.address,
        notes=payload.notes,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(person)
    await db.flush()  # materializa person.id para los FKs de los identifiers

    for ident in payload.identifiers:
        db.add(
            PersonContactIdentifier(
                id=generate_uuid(),
                person_id=person.id,
                channel_type=ident.channel_type.value,
                identifier=ident.identifier,
                is_primary=ident.is_primary,
                verified=ident.verified,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
    await db.flush()

    created = await person_repository.get_full(db, person.id)
    if created is None:  # pragma: no cover - recién insertado, no puede faltar
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(
        db, {created.created_by, created.updated_by}
    )
    return SingleResponse(data=_to_detail(created, audit_users))


async def update(
    db: AsyncSession,
    person_id: str,
    payload: PersonUpdate,
    *,
    actor_id: str,
) -> SingleResponse[PersonDetail]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await person_repository.update(db, person, changes)

    refreshed = await person_repository.get_full(db, person_id)
    if refreshed is None:  # pragma: no cover - recién actualizado, no puede faltar
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(
        db, {refreshed.created_by, refreshed.updated_by}
    )
    return SingleResponse(data=_to_detail(refreshed, audit_users))


async def soft_delete(db: AsyncSession, person_id: str, *, actor_id: str) -> None:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    # Soft-delete de la Person; sus identifiers/lead/customer/assignment/activities
    # quedan colgados pero filtrados por el deleted_at de la persona en cualquier
    # lectura que pase por get_full / search / get_by_identifier.
    person.updated_by = actor_id
    person.updated_on = utc_now()
    await person_repository.soft_delete(db, person)


async def find_by_identifier_or_create(
    db: AsyncSession,
    channel_type: ChannelType,
    identifier: str,
    profile: PersonCreate,
    *,
    campaign_id: str | None = None,
) -> Person:
    """Orquestación del bot (sin endpoint público): resuelve la Person por
    identifier o la crea junto con su lead inicial + asignación round-robin.

    ⚠ Stub F1: la cadena completa (PersonLeadStatus initial + LeadStatusHistory +
    LeadAssignment round-robin + CAMPAIGN_ATTRIBUTION) necesita los modelos de
    F3/F4 que aún no existen. Se completa en F5. NO usar todavía."""
    raise NotImplementedError("find_by_identifier_or_create se completa en F5")
