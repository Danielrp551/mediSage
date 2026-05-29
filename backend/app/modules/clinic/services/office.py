"""
Office service. Module of functions (no classes), per template convention.
Hydrates audit users (`created_by_user`, `updated_by_user`), the denormalized
`branch_name` and `verticals_count` on every Item, and the parent `branch` +
apt `verticals` on every Detail.

The office↔vertical M:N is resolved with `_resolve_verticals` (mirrors
`admin.services.user._resolve_roles`): `vertical_repository.get_by_ids` filters
soft-deleted verticals, so attaching a dead vertical is a 400. Detail paths
reload via `office_repository.get_full` (eager branch + verticals, deleted
verticals filtered) — the same reload-via-get_full pattern catalog uses, since
`create()`/`update()` only refresh column attributes and leave the lazy="raise"
relationships unloaded.
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
from app.modules.catalog.models.vertical import Vertical
from app.modules.catalog.repositories.vertical import vertical_repository
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.clinic.models.office import Office
from app.modules.clinic.repositories.branch import branch_repository
from app.modules.clinic.repositories.office import office_repository
from app.modules.clinic.schemas.branch import BranchOption
from app.modules.clinic.schemas.office import (
    OfficeCreate,
    OfficeDetail,
    OfficeItem,
    OfficeOption,
    OfficeUpdate,
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
    office: Office,
    audit_users: dict[str, User],
    *,
    branch_name: str = "",
    verticals_count: int = 0,
) -> OfficeItem:
    return OfficeItem(
        id=office.id,
        branch_id=office.branch_id,
        branch_name=branch_name,
        code=office.code,
        name=office.name,
        room_number=office.room_number,
        floor=office.floor,
        description=office.description,
        active=office.active,
        verticals_count=verticals_count,
        created_on=office.created_on,
        created_by=office.created_by,
        created_by_user=_audit_info(audit_users.get(office.created_by)),
        updated_on=office.updated_on,
        updated_by=office.updated_by,
        updated_by_user=_audit_info(audit_users.get(office.updated_by)),
    )


def _to_detail(office: Office, audit_users: dict[str, User]) -> OfficeDetail:
    # `office.branch` and `office.verticals` must be eager-loaded by the caller
    # (get_full) — both relationships are `lazy="raise"`. verticals is already
    # filtered to non-deleted by the with_loader_criteria in get_full.
    return OfficeDetail(
        **_to_item(
            office,
            audit_users,
            branch_name=office.branch.name,
            verticals_count=len(office.verticals),
        ).model_dump(),
        branch=BranchOption.model_validate(office.branch, from_attributes=True),
        verticals=[
            VerticalOption.model_validate(v, from_attributes=True) for v in office.verticals
        ],
    )


def _collect_actor_ids(rows: list[Office]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _resolve_verticals(db: AsyncSession, vertical_ids: list[str]) -> list[Vertical]:
    if not vertical_ids:
        return []
    # get_by_ids filters deleted_at IS NULL — a soft-deleted vertical is
    # "unknown" for the purpose of attaching it to an office.
    verticals = await vertical_repository.get_by_ids(db, vertical_ids)
    if len(verticals) != len(set(vertical_ids)):
        found = {v.id for v in verticals}
        missing = sorted(set(vertical_ids) - found)
        # User-facing detail in Spanish (surfaced verbatim in the office form).
        raise BadRequestException(f"Vertical(es) no encontrada(s): {', '.join(missing)}")
    return verticals


async def list_active(
    db: AsyncSession, branch_id: str | None = None, vertical_id: str | None = None
) -> list[OfficeOption]:
    """List active offices for dropdowns, optionally scoped by branch and/or
    apt vertical. Returns the raw list (no envelope), consistent with the rest
    of the module."""
    rows = await office_repository.list_active(db, branch_id=branch_id, vertical_id=vertical_id)
    return [OfficeOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, office_id: str) -> SingleResponse[OfficeDetail]:
    office = await office_repository.get_full(db, office_id)
    if office is None:
        raise NotFoundException("Consultorio no encontrado")
    audit_users = await user_repository.get_audit_info_map(
        db, {office.created_by, office.updated_by}
    )
    return SingleResponse(data=_to_detail(office, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[OfficeItem]:
    items, total = await office_repository.get_paginated(db, query_request)
    # Two batch lookups, no N+1: branch names + apt-vertical counts.
    branch_names = await office_repository.branch_name_map(db, [o.branch_id for o in items])
    vcounts = await office_repository.count_apt_verticals_map(db, [o.id for o in items])
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[
                _to_item(
                    o,
                    audit_users,
                    branch_name=branch_names.get(o.branch_id, ""),
                    verticals_count=vcounts.get(o.id, 0),
                )
                for o in items
            ],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: OfficeCreate, *, actor_id: str
) -> SingleResponse[OfficeDetail]:
    branch = await branch_repository.get_by_id(db, payload.branch_id)
    if branch is None:
        raise NotFoundException("La sede indicada no existe", code="BRANCH_NOT_FOUND")

    existing = await office_repository.get_by_branch_and_code(db, payload.branch_id, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe un consultorio con el código '{payload.code}' en esta sede",
            code="OFFICE_CODE_TAKEN",
        )

    verticals = await _resolve_verticals(db, payload.vertical_ids)

    now = utc_now()
    office = Office(
        id=generate_uuid(),
        branch_id=payload.branch_id,
        code=payload.code,
        name=payload.name,
        room_number=payload.room_number,
        floor=payload.floor,
        description=payload.description,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        verticals=verticals,
    )
    await office_repository.create(db, office)

    # Reload with branch + verticals eager-loaded — `create()` refreshes only
    # column attributes, leaving the lazy="raise" relationships unloaded.
    created = await office_repository.get_full(db, office.id)
    if created is None:  # pragma: no cover - just inserted, cannot be missing
        raise NotFoundException("Consultorio no encontrado")
    audit_users = await user_repository.get_audit_info_map(
        db, {created.created_by, created.updated_by}
    )
    return SingleResponse(data=_to_detail(created, audit_users))


async def update(
    db: AsyncSession,
    office_id: str,
    payload: OfficeUpdate,
    *,
    actor_id: str,
) -> SingleResponse[OfficeDetail]:
    office = await office_repository.get_full(db, office_id)
    if office is None:
        raise NotFoundException("Consultorio no encontrado")

    changes = payload.model_dump(exclude_unset=True)
    vertical_ids = changes.pop("vertical_ids", None)
    # `code` and `branch_id` are immutable: OfficeUpdate doesn't declare them.
    # Belt-and-suspenders — drop any unexpected slot.
    changes.pop("code", None)
    changes.pop("branch_id", None)

    # Full M:N replace only when vertical_ids is present in the payload.
    if vertical_ids is not None:
        office.verticals = await _resolve_verticals(db, vertical_ids)

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await office_repository.update(db, office, changes)

    # `update()` refreshes the row and expires the loaded relationships; reload.
    refreshed = await office_repository.get_full(db, office_id)
    if refreshed is None:  # pragma: no cover - just updated, cannot be missing
        raise NotFoundException("Consultorio no encontrado")
    audit_users = await user_repository.get_audit_info_map(
        db, {refreshed.created_by, refreshed.updated_by}
    )
    return SingleResponse(data=_to_detail(refreshed, audit_users))


async def soft_delete(db: AsyncSession, office_id: str, *, actor_id: str) -> None:
    office = await office_repository.get_by_id(db, office_id)
    if office is None:
        raise NotFoundException("Consultorio no encontrado")
    # No children guard: an office's hours/closures are internal value aggregates
    # (filtered by the office's deleted_at in any scheduling read), and the
    # office_vertical rows are not "active children". Deleting is always allowed.
    office.updated_by = actor_id
    office.updated_on = utc_now()
    await office_repository.soft_delete(db, office)
