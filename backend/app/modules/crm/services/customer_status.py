"""
CustomerStatus service. Análogo a `lead_status.py` SIN `is_won` (sin
WON_REQUIRES_FINAL). Invariantes: `code` único (409 CUSTOMER_STATUS_CODE_TAKEN),
exactamente un `is_initial` (400 MULTIPLE_INITIAL_STATUS). El delete-guard
CUSTOMER_STATUS_IN_USE (PersonCustomerStatus) se difiere a F4; en F2 borrar limpia
las aristas de transición y soft-deletea.
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
from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.customer_status_transition import CustomerStatusTransition
from app.modules.crm.repositories.customer_status import (
    customer_status_repository,
    customer_status_transition_repository,
)
from app.modules.crm.schemas.customer_status import (
    CustomerStatusCreate,
    CustomerStatusItem,
    CustomerStatusOption,
    CustomerStatusUpdate,
    CustomerTransitionTargets,
)
from app.modules.crm.schemas.lead_status import StatusTransitionUpdate
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


def _to_item(status: CustomerStatus, audit_users: dict[str, User]) -> CustomerStatusItem:
    return CustomerStatusItem(
        id=status.id,
        code=status.code,
        name=status.name,
        description=status.description,
        color=status.color,
        is_initial=status.is_initial,
        is_final=status.is_final,
        display_order=status.display_order,
        active=status.active,
        created_on=status.created_on,
        created_by=status.created_by,
        created_by_user=_audit_info(audit_users.get(status.created_by)),
        updated_on=status.updated_on,
        updated_by=status.updated_by,
        updated_by_user=_audit_info(audit_users.get(status.updated_by)),
    )


def _collect_actor_ids(rows: list[CustomerStatus]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _guard_single_initial(db: AsyncSession, *, exclude_id: str | None = None) -> None:
    if await customer_status_repository.count_initial(db, exclude_id=exclude_id) > 0:
        raise BadRequestException(
            "Ya existe un estado inicial; solo puede haber uno",
            code="MULTIPLE_INITIAL_STATUS",
        )


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[CustomerStatusItem]:
    items, total = await customer_status_repository.get_paginated(db, query_request)
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


async def list_active(db: AsyncSession) -> list[CustomerStatusOption]:
    rows = await customer_status_repository.list_active(db)
    return [CustomerStatusOption.model_validate(r, from_attributes=True) for r in rows]


async def create(
    db: AsyncSession, payload: CustomerStatusCreate, *, actor_id: str
) -> SingleResponse[CustomerStatusItem]:
    existing = await customer_status_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe un estado de cliente con el código '{payload.code}'",
            code="CUSTOMER_STATUS_CODE_TAKEN",
        )
    if payload.is_initial:
        await _guard_single_initial(db)

    now = utc_now()
    status = CustomerStatus(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        color=payload.color or None,
        is_initial=payload.is_initial,
        is_final=payload.is_final,
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
    db: AsyncSession, status_id: str, payload: CustomerStatusUpdate, *, actor_id: str
) -> SingleResponse[CustomerStatusItem]:
    status = await customer_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de cliente no encontrado", code="CUSTOMER_STATUS_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_initial") is True:
        await _guard_single_initial(db, exclude_id=status_id)

    if "color" in changes:
        changes["color"] = changes["color"] or None
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await customer_status_repository.update(db, status, changes)

    audit_users = await user_repository.get_audit_info_map(
        db, {status.created_by, status.updated_by}
    )
    return SingleResponse(data=_to_item(status, audit_users))


async def remove(db: AsyncSession, status_id: str, *, actor_id: str) -> None:
    status = await customer_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de cliente no encontrado", code="CUSTOMER_STATUS_NOT_FOUND")
    await customer_status_transition_repository.delete_referencing(db, status_id)
    status.updated_by = actor_id
    status.updated_on = utc_now()
    await customer_status_repository.soft_delete(db, status)


# ── Matriz de transiciones (ADR-008) ────────────────────────────────


async def _resolve_targets(db: AsyncSession, from_id: str) -> CustomerTransitionTargets:
    to_ids = await customer_status_transition_repository.list_outgoing(db, from_id)
    targets = await customer_status_repository.get_by_ids(db, to_ids)
    return CustomerTransitionTargets(
        from_id=from_id,
        to=[CustomerStatusOption.model_validate(t, from_attributes=True) for t in targets],
    )


async def get_transitions(
    db: AsyncSession, status_id: str
) -> SingleResponse[CustomerTransitionTargets]:
    status = await customer_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de cliente no encontrado", code="CUSTOMER_STATUS_NOT_FOUND")
    return SingleResponse(data=await _resolve_targets(db, status_id))


async def set_transitions(
    db: AsyncSession, status_id: str, payload: StatusTransitionUpdate, *, actor_id: str
) -> SingleResponse[CustomerTransitionTargets]:
    status = await customer_status_repository.get_by_id(db, status_id)
    if status is None:
        raise NotFoundException("Estado de cliente no encontrado", code="CUSTOMER_STATUS_NOT_FOUND")

    to_ids = [tid for tid in payload.to_ids if tid != status_id]
    resolved = await customer_status_repository.get_by_ids(db, to_ids)
    if len(resolved) != len(set(to_ids)):
        raise NotFoundException(
            "Uno de los estados destino no existe", code="CUSTOMER_STATUS_NOT_FOUND"
        )

    now = utc_now()
    await customer_status_transition_repository.delete_outgoing(db, status_id)
    for tid in to_ids:
        db.add(
            CustomerStatusTransition(
                id=generate_uuid(),
                from_customer_status_id=status_id,
                to_customer_status_id=tid,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
    await db.flush()
    return SingleResponse(data=await _resolve_targets(db, status_id))
