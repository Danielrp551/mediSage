from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.modules.admin.models.permission import Permission
from app.modules.admin.models.user import User
from app.modules.admin.repositories.permission import permission_repository
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.admin.schemas.permission import (
    PermissionCreate,
    PermissionItem,
    PermissionOption,
    PermissionUpdate,
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


def _to_item(p: Permission, audit_users: dict[str, User]) -> PermissionItem:
    return PermissionItem(
        id=p.id,
        code=p.code,
        name=p.name,
        description=p.description,
        module=p.module,
        active=p.active,
        created_by=p.created_by,
        created_by_user=_audit_info(audit_users.get(p.created_by)),
        created_on=p.created_on,
        updated_by=p.updated_by,
        updated_by_user=_audit_info(audit_users.get(p.updated_by)),
        updated_on=p.updated_on,
    )


def _collect_actor_ids(rows: list[Permission]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def list_active(db: AsyncSession) -> list[PermissionOption]:
    return [
        PermissionOption.model_validate(p, from_attributes=True)
        for p in await permission_repository.list_active(db)
    ]


async def get_by_id(db: AsyncSession, permission_id: str) -> SingleResponse[PermissionItem]:
    perm = await permission_repository.get_by_id(db, permission_id)
    if perm is None:
        raise NotFoundException("Permission not found")
    audit_users = await user_repository.get_audit_info_map(db, {perm.created_by, perm.updated_by})
    return SingleResponse(data=_to_item(perm, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[PermissionItem]:
    items, total = await permission_repository.get_paginated(db, query_request)
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(p, audit_users) for p in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession,
    payload: PermissionCreate,
    *,
    actor_id: str,
) -> SingleResponse[PermissionItem]:
    existing = await permission_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(f"Permission code '{payload.code}' already exists")

    now = utc_now()
    perm = Permission(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        module=payload.module,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await permission_repository.create(db, perm)
    audit_users = await user_repository.get_audit_info_map(db, {perm.created_by, perm.updated_by})
    return SingleResponse(data=_to_item(perm, audit_users))


async def update(
    db: AsyncSession,
    permission_id: str,
    payload: PermissionUpdate,
    *,
    actor_id: str,
) -> SingleResponse[PermissionItem]:
    perm = await permission_repository.get_by_id(db, permission_id)
    if perm is None:
        raise NotFoundException("Permission not found")

    changes = payload.model_dump(exclude_unset=True)

    if "code" in changes and changes["code"] != perm.code:
        clash = await permission_repository.get_by_code(db, changes["code"])
        if clash is not None:
            raise AlreadyExistsException(f"Permission code '{changes['code']}' already exists")

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await permission_repository.update(db, perm, changes)
    audit_users = await user_repository.get_audit_info_map(db, {perm.created_by, perm.updated_by})
    return SingleResponse(data=_to_item(perm, audit_users))
