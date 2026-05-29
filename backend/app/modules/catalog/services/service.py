"""
Service service. Module of functions (no classes), per template convention.
Hydrates audit users (`created_by_user`, `updated_by_user`) and the
denormalized `vertical_name` on every Item; the parent vertical is eager
batch-loaded via `selectinload` (never N+1).

`products_count` is 0 in phase 2 (the Product model doesn't exist yet);
phase 3 replaces the hardcoded zero with a batch count and adds the
delete-with-active-children guard to `soft_delete`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.models.service import Service
from app.modules.catalog.repositories.service import service_repository
from app.modules.catalog.repositories.vertical import vertical_repository
from app.modules.catalog.schemas.service import (
    ServiceCreate,
    ServiceDetail,
    ServiceItem,
    ServiceOption,
    ServiceUpdate,
)
from app.modules.catalog.schemas.vertical import VerticalOption
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


def _to_item(
    service: Service,
    audit_users: dict[str, User],
    *,
    products_count: int = 0,
) -> ServiceItem:
    # `service.vertical` must be eager-loaded by the caller (selectinload /
    # get_full) — the relationship is `lazy="raise"`.
    return ServiceItem(
        id=service.id,
        vertical_id=service.vertical_id,
        vertical_name=service.vertical.name,
        code=service.code,
        name=service.name,
        description=service.description,
        display_order=service.display_order,
        active=service.active,
        products_count=products_count,
        created_on=service.created_on,
        created_by=service.created_by,
        created_by_user=_audit_info(audit_users.get(service.created_by)),
        updated_on=service.updated_on,
        updated_by=service.updated_by,
        updated_by_user=_audit_info(audit_users.get(service.updated_by)),
    )


def _to_detail(
    service: Service,
    audit_users: dict[str, User],
    *,
    products_count: int = 0,
) -> ServiceDetail:
    return ServiceDetail(
        **_to_item(service, audit_users, products_count=products_count).model_dump(),
        vertical=VerticalOption.model_validate(service.vertical, from_attributes=True),
    )


def _collect_actor_ids(rows: list[Service]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def list_active(db: AsyncSession, vertical_id: str | None = None) -> list[ServiceOption]:
    """List active services for dropdowns, optionally scoped to one vertical.
    Returns the raw list (no envelope), consistent with `list_active` in the
    admin and vertical services."""
    rows = await service_repository.list_active(db, vertical_id=vertical_id)
    return [ServiceOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, service_id: str) -> SingleResponse[ServiceDetail]:
    service = await service_repository.get_full(db, service_id)
    if service is None:
        raise NotFoundException("Service not found")
    audit_users = await user_repository.get_audit_info_map(
        db, {service.created_by, service.updated_by}
    )
    return SingleResponse(data=_to_detail(service, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[ServiceItem]:
    items, total = await service_repository.get_paginated(
        db, query_request, load=(selectinload(Service.vertical),)
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(s, audit_users) for s in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: ServiceCreate, *, actor_id: str
) -> SingleResponse[ServiceDetail]:
    vertical = await vertical_repository.get_by_id(db, payload.vertical_id)
    if vertical is None:
        raise NotFoundException("Vertical not found", code="VERTICAL_NOT_FOUND")

    existing = await service_repository.get_by_vertical_and_code(
        db, payload.vertical_id, payload.code
    )
    if existing is not None:
        raise AlreadyExistsException(
            f"Service with code '{payload.code}' already exists in this vertical",
            code="SERVICE_CODE_TAKEN",
        )

    now = utc_now()
    service = Service(
        id=generate_uuid(),
        vertical_id=payload.vertical_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        display_order=payload.display_order,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await service_repository.create(db, service)

    # Reload with the parent eager-loaded — `create()` refreshes only column
    # attributes, leaving `service.vertical` unloaded (lazy="raise").
    created = await service_repository.get_full(db, service.id)
    if created is None:  # pragma: no cover - just inserted, cannot be missing
        raise NotFoundException("Service not found")
    audit_users = await user_repository.get_audit_info_map(
        db, {created.created_by, created.updated_by}
    )
    return SingleResponse(data=_to_detail(created, audit_users))


async def update(
    db: AsyncSession,
    service_id: str,
    payload: ServiceUpdate,
    *,
    actor_id: str,
) -> SingleResponse[ServiceDetail]:
    service = await service_repository.get_full(db, service_id)
    if service is None:
        raise NotFoundException("Service not found")

    changes = payload.model_dump(exclude_unset=True)
    # `code` and `vertical_id` are immutable: ServiceUpdate doesn't declare
    # them. Belt-and-suspenders — drop any unexpected slot.
    changes.pop("code", None)
    changes.pop("vertical_id", None)
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()

    await service_repository.update(db, service, changes)

    # `update()` refreshes the row and expires the loaded vertical; reload it.
    refreshed = await service_repository.get_full(db, service_id)
    if refreshed is None:  # pragma: no cover - just updated, cannot be missing
        raise NotFoundException("Service not found")
    audit_users = await user_repository.get_audit_info_map(
        db, {refreshed.created_by, refreshed.updated_by}
    )
    return SingleResponse(data=_to_detail(refreshed, audit_users))


async def soft_delete(db: AsyncSession, service_id: str, *, actor_id: str) -> None:
    service = await service_repository.get_by_id(db, service_id)
    if service is None:
        raise NotFoundException("Service not found")
    # Phase 3 will guard against deleting a service with active products here:
    #   active_products = await service_repository.count_active_products(db, service_id)
    #   if active_products > 0:
    #       raise ConflictException(
    #           f"Cannot delete service with {active_products} active product(s).",
    #           code="SERVICE_HAS_ACTIVE_CHILDREN",
    #       )
    service.updated_by = actor_id
    service.updated_on = utc_now()
    await service_repository.soft_delete(db, service)
