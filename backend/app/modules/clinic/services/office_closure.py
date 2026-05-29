"""
OfficeClosure service. Module of functions (no classes), per template
convention. Closures are individual CRUD units (create / list / delete — no
update; to fix one, delete and recreate). Hydrates audit users on every Item.

User-facing exception details are Spanish (surfaced verbatim); `code` stays
English for frontend branching; Pydantic validator messages stay English (the
frontend re-validates with Zod).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.clinic.models.office_closure import OfficeClosure
from app.modules.clinic.repositories.office import office_repository
from app.modules.clinic.repositories.office_closure import office_closure_repository
from app.modules.clinic.schemas.office_closure import (
    OfficeClosureCreate,
    OfficeClosureDetail,
    OfficeClosureItem,
)
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(closure: OfficeClosure, audit_users: dict[str, User]) -> OfficeClosureItem:
    return OfficeClosureItem(
        id=closure.id,
        office_id=closure.office_id,
        starts_at=closure.starts_at,
        ends_at=closure.ends_at,
        is_closed=closure.is_closed,
        reason=closure.reason,
        active=closure.active,
        created_on=closure.created_on,
        created_by=closure.created_by,
        created_by_user=_audit_info(audit_users.get(closure.created_by)),
        updated_on=closure.updated_on,
        updated_by=closure.updated_by,
        updated_by_user=_audit_info(audit_users.get(closure.updated_by)),
    )


def _collect_actor_ids(rows: list[OfficeClosure]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _require_office(db: AsyncSession, office_id: str) -> None:
    office = await office_repository.get_by_id(db, office_id)
    if office is None:
        raise NotFoundException("Consultorio no encontrado", code="OFFICE_NOT_FOUND")


async def list_for_office(
    db: AsyncSession,
    office_id: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> SingleResponse[list[OfficeClosureItem]]:
    await _require_office(db, office_id)
    rows = await office_closure_repository.list_for_office(db, office_id, date_from, date_to)
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(rows))
    return SingleResponse(data=[_to_item(r, audit_users) for r in rows])


async def create(
    db: AsyncSession,
    office_id: str,
    payload: OfficeClosureCreate,
    *,
    actor_id: str,
) -> SingleResponse[OfficeClosureDetail]:
    await _require_office(db, office_id)

    now = utc_now()
    closure = OfficeClosure(
        id=generate_uuid(),
        office_id=office_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        is_closed=payload.is_closed,
        reason=payload.reason,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await office_closure_repository.create(db, closure)
    audit_users = await user_repository.get_audit_info_map(
        db, {closure.created_by, closure.updated_by}
    )
    return SingleResponse(data=OfficeClosureDetail(**_to_item(closure, audit_users).model_dump()))


async def soft_delete(db: AsyncSession, office_id: str, closure_id: str, *, actor_id: str) -> None:
    closure = await office_closure_repository.get_by_id(db, closure_id)
    # Ownership check: the closure must exist AND belong to this office (a
    # closure_id from another office must not be deletable through this path).
    if closure is None or closure.office_id != office_id:
        raise NotFoundException("Excepción no encontrada", code="CLOSURE_NOT_FOUND")
    closure.updated_by = actor_id
    closure.updated_on = utc_now()
    await office_closure_repository.soft_delete(db, closure)
