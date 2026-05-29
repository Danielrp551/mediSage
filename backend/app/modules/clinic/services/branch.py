"""
Branch service. Module of functions (no classes), per template convention.
Hydrates audit users (`created_by_user`, `updated_by_user`) on every Item via
batch lookup, matching the pattern from `catalog.services.vertical`.

`offices_count` is live as of phase 2: the paginated list uses one batch count
query and the single-branch paths count on demand; `soft_delete` guards against
deleting a branch that still has active (non-deleted) offices.
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
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.repositories.branch import branch_repository
from app.modules.clinic.schemas.branch import (
    BranchCreate,
    BranchDetail,
    BranchItem,
    BranchOption,
    BranchUpdate,
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
    branch: Branch,
    audit_users: dict[str, User],
    *,
    offices_count: int = 0,
) -> BranchItem:
    return BranchItem(
        id=branch.id,
        code=branch.code,
        name=branch.name,
        address_line=branch.address_line,
        district=branch.district,
        city=branch.city,
        region=branch.region,
        country=branch.country,
        postal_code=branch.postal_code,
        latitude=branch.latitude,
        longitude=branch.longitude,
        phone=branch.phone,
        email=branch.email,
        timezone=branch.timezone,
        active=branch.active,
        offices_count=offices_count,
        created_on=branch.created_on,
        created_by=branch.created_by,
        created_by_user=_audit_info(audit_users.get(branch.created_by)),
        updated_on=branch.updated_on,
        updated_by=branch.updated_by,
        updated_by_user=_audit_info(audit_users.get(branch.updated_by)),
    )


def _to_detail(
    branch: Branch, audit_users: dict[str, User], *, offices_count: int = 0
) -> BranchDetail:
    return BranchDetail(**_to_item(branch, audit_users, offices_count=offices_count).model_dump())


def _collect_actor_ids(rows: list[Branch]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def list_active(db: AsyncSession) -> list[BranchOption]:
    """List active branches for dropdowns. Returns the raw list (no envelope),
    consistent with `catalog.services.vertical.list_active`."""
    rows = await branch_repository.list_active(db)
    return [BranchOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, branch_id: str) -> SingleResponse[BranchDetail]:
    branch = await branch_repository.get_by_id(db, branch_id)
    if branch is None:
        raise NotFoundException("Branch not found")
    offices_count = await branch_repository.count_active_offices(db, branch_id)
    audit_users = await user_repository.get_audit_info_map(
        db, {branch.created_by, branch.updated_by}
    )
    return SingleResponse(data=_to_detail(branch, audit_users, offices_count=offices_count))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[BranchItem]:
    items, total = await branch_repository.get_paginated(db, query_request)
    counts = await branch_repository.count_active_offices_map(db, [b.id for b in items])
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(b, audit_users, offices_count=counts.get(b.id, 0)) for b in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: BranchCreate, *, actor_id: str
) -> SingleResponse[BranchDetail]:
    existing = await branch_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Branch with code '{payload.code}' already exists",
            code="BRANCH_CODE_TAKEN",
        )

    now = utc_now()
    branch = Branch(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        address_line=payload.address_line,
        district=payload.district,
        city=payload.city,
        region=payload.region,
        country=payload.country,
        postal_code=payload.postal_code,
        latitude=payload.latitude,
        longitude=payload.longitude,
        phone=payload.phone,
        email=payload.email,
        timezone=payload.timezone,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await branch_repository.create(db, branch)
    audit_users = await user_repository.get_audit_info_map(
        db, {branch.created_by, branch.updated_by}
    )
    return SingleResponse(data=_to_detail(branch, audit_users))


async def update(
    db: AsyncSession,
    branch_id: str,
    payload: BranchUpdate,
    *,
    actor_id: str,
) -> SingleResponse[BranchDetail]:
    branch = await branch_repository.get_by_id(db, branch_id)
    if branch is None:
        raise NotFoundException("Branch not found")

    changes = payload.model_dump(exclude_unset=True)
    # `code` is immutable: BranchUpdate doesn't declare it. Belt-and-suspenders.
    changes.pop("code", None)
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()

    await branch_repository.update(db, branch, changes)
    offices_count = await branch_repository.count_active_offices(db, branch_id)
    audit_users = await user_repository.get_audit_info_map(
        db, {branch.created_by, branch.updated_by}
    )
    return SingleResponse(data=_to_detail(branch, audit_users, offices_count=offices_count))


async def soft_delete(db: AsyncSession, branch_id: str, *, actor_id: str) -> None:
    branch = await branch_repository.get_by_id(db, branch_id)
    if branch is None:
        raise NotFoundException("Branch not found")
    # "Active" here = not soft-deleted (a merely disabled office still holds the
    # FK), so the guard counts every non-deleted office. Deleting them unblocks.
    active_offices = await branch_repository.count_active_offices(db, branch_id)
    if active_offices > 0:
        # User-facing detail in Spanish (surfaced verbatim in the delete dialog,
        # see ui.md copy table). Domain-exception details that reach the UI are
        # Spanish; Pydantic validator messages stay English (the frontend
        # re-validates with Zod). `code` stays English for frontend branching.
        raise ConflictException(
            f"No se puede eliminar — la sede tiene {active_offices} consultorio(s) "
            "activo(s). Deshabilítalos o elimínalos primero.",
            code="BRANCH_HAS_ACTIVE_CHILDREN",
        )
    branch.updated_by = actor_id
    branch.updated_on = utc_now()
    await branch_repository.soft_delete(db, branch)
