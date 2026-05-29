"""
Vertical service. Module of functions (no classes), per template convention.
Hydrates audit users (`created_by_user`, `updated_by_user`) on every Item
via batch lookup, matching the pattern from `admin.services.role`.

`services_count` is live as of phase 2: the paginated list uses one batch
count query and the single-vertical paths count on demand. `products_count`
stays 0 until phase 3 adds the Product model.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyExistsException,
    ConflictException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.models.vertical import Vertical
from app.modules.catalog.repositories.vertical import vertical_repository
from app.modules.catalog.schemas.vertical import (
    VerticalCreate,
    VerticalDetail,
    VerticalItem,
    VerticalOption,
    VerticalUpdate,
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


def _to_item(
    vertical: Vertical,
    audit_users: dict[str, User],
    *,
    services_count: int = 0,
    products_count: int = 0,
) -> VerticalItem:
    return VerticalItem(
        id=vertical.id,
        code=vertical.code,
        name=vertical.name,
        description=vertical.description,
        color=vertical.color,
        icon=vertical.icon,
        display_order=vertical.display_order,
        active=vertical.active,
        services_count=services_count,
        products_count=products_count,
        created_on=vertical.created_on,
        created_by=vertical.created_by,
        created_by_user=_audit_info(audit_users.get(vertical.created_by)),
        updated_on=vertical.updated_on,
        updated_by=vertical.updated_by,
        updated_by_user=_audit_info(audit_users.get(vertical.updated_by)),
    )


def _to_detail(
    vertical: Vertical,
    audit_users: dict[str, User],
    *,
    services_count: int = 0,
    products_count: int = 0,
) -> VerticalDetail:
    return VerticalDetail(
        **_to_item(
            vertical,
            audit_users,
            services_count=services_count,
            products_count=products_count,
        ).model_dump()
    )


def _collect_actor_ids(rows: list[Vertical]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def list_active(db: AsyncSession) -> list[VerticalOption]:
    """List active verticals for dropdowns. Returns the raw list (no
    envelope), consistent with `admin.services.role.list_active`."""
    rows = await vertical_repository.list_active(db)
    return [VerticalOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, vertical_id: str) -> SingleResponse[VerticalDetail]:
    vertical = await vertical_repository.get_by_id(db, vertical_id)
    if vertical is None:
        raise NotFoundException("Vertical not found")
    services_count = await vertical_repository.count_active_services(db, vertical_id)
    audit_users = await user_repository.get_audit_info_map(
        db, {vertical.created_by, vertical.updated_by}
    )
    return SingleResponse(data=_to_detail(vertical, audit_users, services_count=services_count))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[VerticalItem]:
    items, total = await vertical_repository.get_paginated(db, query_request)
    counts = await vertical_repository.count_active_services_map(db, [v.id for v in items])
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(v, audit_users, services_count=counts.get(v.id, 0)) for v in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: VerticalCreate, *, actor_id: str
) -> SingleResponse[VerticalDetail]:
    existing = await vertical_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Vertical with code '{payload.code}' already exists",
            code="VERTICAL_CODE_TAKEN",
        )

    now = utc_now()
    vertical = Vertical(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        display_order=payload.display_order,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await vertical_repository.create(db, vertical)
    audit_users = await user_repository.get_audit_info_map(
        db, {vertical.created_by, vertical.updated_by}
    )
    return SingleResponse(data=_to_detail(vertical, audit_users))


async def update(
    db: AsyncSession,
    vertical_id: str,
    payload: VerticalUpdate,
    *,
    actor_id: str,
) -> SingleResponse[VerticalDetail]:
    vertical = await vertical_repository.get_by_id(db, vertical_id)
    if vertical is None:
        raise NotFoundException("Vertical not found")

    changes = payload.model_dump(exclude_unset=True)
    # `code` is immutable: VerticalUpdate doesn't even declare it. Belt-and-
    # suspenders: drop any unexpected slot to keep the contract explicit.
    changes.pop("code", None)
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()

    await vertical_repository.update(db, vertical, changes)
    services_count = await vertical_repository.count_active_services(db, vertical_id)
    audit_users = await user_repository.get_audit_info_map(
        db, {vertical.created_by, vertical.updated_by}
    )
    return SingleResponse(data=_to_detail(vertical, audit_users, services_count=services_count))


async def soft_delete(db: AsyncSession, vertical_id: str, *, actor_id: str) -> None:
    vertical = await vertical_repository.get_by_id(db, vertical_id)
    if vertical is None:
        raise NotFoundException("Vertical not found")
    # A vertical with live children must not vanish under them. "Live" means
    # not soft-deleted (a merely disabled service still holds the FK), so the
    # guard counts every non-deleted child and deleting them is what unblocks.
    child_services = await vertical_repository.count_active_services(db, vertical_id)
    if child_services > 0:
        raise ConflictException(
            f"Cannot delete vertical with {child_services} service(s) still attached. "
            "Delete its services first.",
            code="VERTICAL_HAS_ACTIVE_CHILDREN",
        )
    vertical.updated_by = actor_id
    vertical.updated_on = utc_now()
    await vertical_repository.soft_delete(db, vertical)
