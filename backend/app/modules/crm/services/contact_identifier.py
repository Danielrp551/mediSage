"""
PersonContactIdentifier service. Módulo de funciones (no clases). CRUD anidado
bajo `/persons/{id}/identifiers`:
- list: identificadores vivos de la persona (hidrata audit users, sin N+1).
- add: dedup proactivo (409 IDENTIFIER_TAKEN) + is_primary único por canal.
- update: editar canal/valor re-dispara la dedup; togglear is_primary desmarca el
  principal anterior del mismo canal en la misma tx.
- remove: soft-delete (404 IDENTIFIER_NOT_FOUND si no es de esa persona).

La persona debe existir y estar viva (404 PERSON_NOT_FOUND). El ownership de cada
identifier se verifica con `get_for_person` (404 IDENTIFIER_NOT_FOUND).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.modules.crm.repositories.contact_identifier import contact_identifier_repository
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.schemas.contact_identifier import (
    ContactIdentifierCreate,
    ContactIdentifierItem,
    ContactIdentifierUpdate,
)
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(
    identifier: PersonContactIdentifier, audit_users: dict[str, User]
) -> ContactIdentifierItem:
    return ContactIdentifierItem(
        id=identifier.id,
        person_id=identifier.person_id,
        channel_type=identifier.channel_type,
        identifier=identifier.identifier,
        is_primary=identifier.is_primary,
        verified=identifier.verified,
        active=identifier.active,
        created_on=identifier.created_on,
        created_by=identifier.created_by,
        created_by_user=_audit_info(audit_users.get(identifier.created_by)),
        updated_on=identifier.updated_on,
        updated_by=identifier.updated_by,
        updated_by_user=_audit_info(audit_users.get(identifier.updated_by)),
    )


def _collect_actor_ids(rows: list[PersonContactIdentifier]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _require_person(db: AsyncSession, person_id: str) -> None:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")


async def _guard_identifier_unique(db: AsyncSession, channel_type: str, identifier: str) -> None:
    existing = await person_repository.get_by_identifier(db, channel_type, identifier)
    if existing is not None:
        raise AlreadyExistsException(
            f"El identificador '{channel_type}:{identifier}' ya está registrado",
            code="IDENTIFIER_TAKEN",
        )


async def list_for_person(
    db: AsyncSession, person_id: str
) -> SingleResponse[list[ContactIdentifierItem]]:
    await _require_person(db, person_id)
    rows = await contact_identifier_repository.list_for_person(db, person_id)
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(rows))
    return SingleResponse(data=[_to_item(r, audit_users) for r in rows])


async def add(
    db: AsyncSession, person_id: str, payload: ContactIdentifierCreate, *, actor_id: str
) -> SingleResponse[ContactIdentifierItem]:
    await _require_person(db, person_id)
    await _guard_identifier_unique(db, payload.channel_type.value, payload.identifier)

    now = utc_now()
    if payload.is_primary:
        # Desmarca el principal anterior del mismo canal (misma tx).
        await contact_identifier_repository.unmark_primary(
            db, person_id, payload.channel_type.value, actor_id=actor_id, now=now
        )
    identifier = PersonContactIdentifier(
        id=generate_uuid(),
        person_id=person_id,
        channel_type=payload.channel_type.value,
        identifier=payload.identifier,
        is_primary=payload.is_primary,
        verified=payload.verified,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(identifier)
    await db.flush()

    audit_users = await user_repository.get_audit_info_map(
        db, {identifier.created_by, identifier.updated_by}
    )
    return SingleResponse(data=_to_item(identifier, audit_users))


async def update(
    db: AsyncSession,
    person_id: str,
    identifier_id: str,
    payload: ContactIdentifierUpdate,
    *,
    actor_id: str,
) -> SingleResponse[ContactIdentifierItem]:
    await _require_person(db, person_id)
    identifier = await contact_identifier_repository.get_for_person(db, person_id, identifier_id)
    if identifier is None:
        raise NotFoundException("Identificador no encontrado", code="IDENTIFIER_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    now = utc_now()

    # Si cambia el canal y/o el valor, re-disparar la dedup contra el nuevo par.
    # `channel_type` viene como ChannelType (StrEnum) desde model_dump; str() da el
    # slug, idéntico a lo que guarda la columna varchar.
    channel_value = str(changes.get("channel_type", identifier.channel_type))
    new_value = str(changes.get("identifier", identifier.identifier))
    if (channel_value, new_value) != (identifier.channel_type, identifier.identifier):
        await _guard_identifier_unique(db, channel_value, new_value)

    # Normaliza el enum a su slug antes de persistir (la columna es varchar).
    if "channel_type" in changes:
        changes["channel_type"] = channel_value

    # Marcar is_primary=true desmarca el principal anterior del mismo canal.
    if changes.get("is_primary") is True:
        await contact_identifier_repository.unmark_primary(
            db,
            person_id,
            channel_value,
            exclude_id=identifier.id,
            actor_id=actor_id,
            now=now,
        )

    changes["updated_by"] = actor_id
    changes["updated_on"] = now
    await contact_identifier_repository.update(db, identifier, changes)

    audit_users = await user_repository.get_audit_info_map(
        db, {identifier.created_by, identifier.updated_by}
    )
    return SingleResponse(data=_to_item(identifier, audit_users))


async def remove(db: AsyncSession, person_id: str, identifier_id: str, *, actor_id: str) -> None:
    await _require_person(db, person_id)
    identifier = await contact_identifier_repository.get_for_person(db, person_id, identifier_id)
    if identifier is None:
        raise NotFoundException("Identificador no encontrado", code="IDENTIFIER_NOT_FOUND")
    identifier.updated_by = actor_id
    identifier.updated_on = utc_now()
    await contact_identifier_repository.soft_delete(db, identifier)
