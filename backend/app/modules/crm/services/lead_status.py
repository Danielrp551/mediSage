"""
LeadStatus service. Módulo de funciones (no clases). CRUD del catálogo de estados
de lead + la matriz de transiciones (ADR-008).

Invariantes (validados acá, NO en Pydantic, para devolver 400 + code consistente):
- `code` único → 409 LEAD_STATUS_CODE_TAKEN.
- exactamente un `is_initial` por catálogo → 400 MULTIPLE_INITIAL_STATUS.
- `is_won ⟹ is_final` → 400 WON_REQUIRES_FINAL (create y update, sobre el merge).

⚠ Subset F2: el delete-guard `LEAD_STATUS_IN_USE` (que mira PersonLeadStatus) se
difiere a F3 — esa tabla no existe todavía. En F2, borrar un estado limpia sus
aristas de transición (no quedan colgantes) y lo soft-deletea. La matriz SÍ es
construible en F2 (FKs a lead_status, que ya existe).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyExistsException,
    BadRequestException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_transition import LeadStatusTransition
from app.modules.crm.repositories.lead_status import (
    lead_status_repository,
    lead_status_transition_repository,
)
from app.modules.crm.schemas.lead_status import (
    LeadStatusCreate,
    LeadStatusItem,
    LeadStatusOption,
    LeadStatusUpdate,
    StatusTransitionUpdate,
    TransitionTargets,
)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(status: LeadStatus, audit_users: dict[str, User]) -> LeadStatusItem:
    return LeadStatusItem(
        id=status.id,
        code=status.code,
        name=status.name,
        description=status.description,
        color=status.color,
        is_initial=status.is_initial,
        is_final=status.is_final,
        is_won=status.is_won,
        display_order=status.display_order,
        active=status.active,
        created_on=status.created_on,
        created_by=status.created_by,
        created_by_user=_audit_info(audit_users.get(status.created_by)),
        updated_on=status.updated_on,
        updated_by=status.updated_by,
        updated_by_user=_audit_info(audit_users.get(status.updated_by)),
    )


def _collect_actor_ids(rows: list[LeadStatus]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


def _validate_won_requires_final(*, is_won: bool, is_final: bool) -> None:
    if is_won and not is_final:
        raise BadRequestException(
            "Un estado ganado debe ser también final", code="WON_REQUIRES_FINAL"
        )


async def _guard_single_initial(db: AsyncSession, *, exclude_id: str | None = None) -> None:
    if await lead_status_repository.count_initial(db, exclude_id=exclude_id) > 0:
        raise BadRequestException(
            "Ya existe un estado inicial; solo puede haber uno",
            code="MULTIPLE_INITIAL_STATUS",
        )


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[LeadStatusItem]:
    items, total = await lead_status_repository.get_paginated(db, query_request)
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    rows = [_to_item(s, audit_users) for s in items]
    return PaginatedResponse(
        data=PaginatedData(
            items=rows,
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def list_active(db: AsyncSession) -> list[LeadStatusOption]:
    """Lista cruda de estados vivos (sin envelope) — dropdowns y editor de matriz."""
    rows = await lead_status_repository.list_active(db)
    return [LeadStatusOption.model_validate(r, from_attributes=True) for r in rows]


async def create(
    db: AsyncSession, payload: LeadStatusCreate, *, actor_id: str
) -> SingleResponse[LeadStatusItem]:
    existing = await lead_status_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe un estado de lead con el código '{payload.code}'",
            code="LEAD_STATUS_CODE_TAKEN",
        )
    _validate_won_requires_final(is_won=payload.is_won, is_final=payload.is_final)
    if payload.is_initial:
        await _guard_single_initial(db)

    now = utc_now()
    status = LeadStatus(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        color=payload.color or None,
        is_initial=payload.is_initial,
        is_final=payload.is_final,
        is_won=payload.is_won,
        display_order=payload.display_order,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(status)
    await db.flush()

    audit_users = await user_repository.get_audit_info_map(
        db, {status.created_by, status.updated_by}
    )
    return SingleResponse(data=_to_item(status, audit_users))


async def update(
    db: AsyncSession, status_id: str, payload: LeadStatusUpdate, *, actor_id: str
) -> SingleResponse[LeadStatusItem]:
    status = await lead_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)

    # Revalidar los invariantes sobre el MERGE (el código no se renombra).
    merged_is_final = changes.get("is_final", status.is_final)
    merged_is_won = changes.get("is_won", status.is_won)
    _validate_won_requires_final(is_won=merged_is_won, is_final=merged_is_final)
    if changes.get("is_initial") is True:
        await _guard_single_initial(db, exclude_id=status_id)

    if "color" in changes:
        changes["color"] = changes["color"] or None
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await lead_status_repository.update(db, status, changes)

    audit_users = await user_repository.get_audit_info_map(
        db, {status.created_by, status.updated_by}
    )
    return SingleResponse(data=_to_item(status, audit_users))


async def remove(db: AsyncSession, status_id: str, *, actor_id: str) -> None:
    status = await lead_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")
    # F2: LEAD_STATUS_IN_USE (PersonLeadStatus) se difiere a F3. Limpiamos las aristas
    # de transición que tocan el estado (sin SD → DELETE real) para no dejar la matriz
    # colgando, y soft-deleteamos el catálogo.
    await lead_status_transition_repository.delete_referencing(db, status_id)
    status.updated_by = actor_id
    status.updated_on = utc_now()
    await lead_status_repository.soft_delete(db, status)


# ── Matriz de transiciones (ADR-008) ────────────────────────────────


async def _resolve_targets(db: AsyncSession, from_id: str) -> TransitionTargets:
    to_ids = await lead_status_transition_repository.list_outgoing(db, from_id)
    targets = await lead_status_repository.get_by_ids(db, to_ids)
    return TransitionTargets(
        from_id=from_id,
        to=[LeadStatusOption.model_validate(t, from_attributes=True) for t in targets],
    )


async def get_transitions(db: AsyncSession, status_id: str) -> SingleResponse[TransitionTargets]:
    status = await lead_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")
    return SingleResponse(data=await _resolve_targets(db, status_id))


async def set_transitions(
    db: AsyncSession, status_id: str, payload: StatusTransitionUpdate, *, actor_id: str
) -> SingleResponse[TransitionTargets]:
    status = await lead_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")

    # Un estado no transiciona a sí mismo (defensivo; el front ya lo excluye).
    to_ids = [tid for tid in payload.to_ids if tid != status_id]
    resolved = await lead_status_repository.get_by_ids(db, to_ids)
    if len(resolved) != len(set(to_ids)):
        raise NotFoundException(
            "Uno de los estados destino no existe", code="LEAD_STATUS_NOT_FOUND"
        )

    now = utc_now()
    await lead_status_transition_repository.delete_outgoing(db, status_id)
    for tid in to_ids:
        db.add(
            LeadStatusTransition(
                id=generate_uuid(),
                from_lead_status_id=status_id,
                to_lead_status_id=tid,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
    await db.flush()
    return SingleResponse(data=await _resolve_targets(db, status_id))
