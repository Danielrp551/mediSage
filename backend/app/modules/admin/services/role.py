from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AlreadyExistsException, BadRequestException, NotFoundException
from app.modules.admin.models.role import Role
from app.modules.admin.models.user import User
from app.modules.admin.repositories.permission import permission_repository
from app.modules.admin.repositories.role import role_repository
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.admin.schemas.permission import PermissionOption
from app.modules.admin.schemas.role import (
    RoleCreate,
    RoleDetail,
    RoleItem,
    RoleOption,
    RoleUpdate,
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


def _to_item(role: Role, audit_users: dict[str, User]) -> RoleItem:
    return RoleItem(
        id=role.id,
        name=role.name,
        description=role.description,
        active=role.active,
        permissions_count=len(role.permissions),
        created_by=role.created_by,
        created_by_user=_audit_info(audit_users.get(role.created_by)),
        created_on=role.created_on,
        updated_by=role.updated_by,
        updated_by_user=_audit_info(audit_users.get(role.updated_by)),
        updated_on=role.updated_on,
    )


def _to_detail(role: Role, audit_users: dict[str, User]) -> RoleDetail:
    return RoleDetail(
        **_to_item(role, audit_users).model_dump(),
        permissions=[
            PermissionOption.model_validate(p, from_attributes=True) for p in role.permissions
        ],
    )


def _collect_actor_ids(rows: list[Role]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _resolve_permissions(db: AsyncSession, permission_ids: list[str]):
    if not permission_ids:
        return []
    perms = await permission_repository.get_by_ids(db, permission_ids)
    if len(perms) != len(set(permission_ids)):
        found = {p.id for p in perms}
        missing = sorted(set(permission_ids) - found)
        raise BadRequestException(f"Unknown permission(s): {', '.join(missing)}")
    inactive = [p.code for p in perms if not p.active]
    if inactive:
        raise BadRequestException(f"Cannot assign inactive permission(s): {', '.join(inactive)}")
    return perms


async def list_active(db: AsyncSession) -> list[RoleOption]:
    return [
        RoleOption.model_validate(r, from_attributes=True)
        for r in await role_repository.list_active(db)
    ]


async def get_by_id(db: AsyncSession, role_id: str) -> SingleResponse[RoleDetail]:
    role = await role_repository.get_by_id(db, role_id, load=(selectinload(Role.permissions),))
    if role is None:
        raise NotFoundException("Role not found")
    audit_users = await user_repository.get_audit_info_map(db, {role.created_by, role.updated_by})
    return SingleResponse(data=_to_detail(role, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[RoleItem]:
    items, total = await role_repository.get_paginated(
        db, query_request, load=(selectinload(Role.permissions),)
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(r, audit_users) for r in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: RoleCreate, *, actor_id: str
) -> SingleResponse[RoleDetail]:
    if await role_repository.get_by_name(db, payload.name):
        raise AlreadyExistsException(f"Role '{payload.name}' already exists")

    permissions = await _resolve_permissions(db, payload.permission_ids)

    now = utc_now()
    role = Role(
        id=generate_uuid(),
        name=payload.name,
        description=payload.description,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        permissions=permissions,
    )
    await role_repository.create(db, role)
    audit_users = await user_repository.get_audit_info_map(db, {role.created_by, role.updated_by})
    return SingleResponse(data=_to_detail(role, audit_users))


async def update(
    db: AsyncSession,
    role_id: str,
    payload: RoleUpdate,
    *,
    actor_id: str,
) -> SingleResponse[RoleDetail]:
    role = await role_repository.get_by_id(db, role_id, load=(selectinload(Role.permissions),))
    if role is None:
        raise NotFoundException("Role not found")

    changes = payload.model_dump(exclude_unset=True)
    permission_ids = changes.pop("permission_ids", None)

    if "name" in changes and changes["name"] != role.name:
        clash = await role_repository.get_by_name(db, changes["name"])
        if clash is not None:
            raise AlreadyExistsException(f"Role '{changes['name']}' already exists")

    if permission_ids is not None:
        role.permissions = await _resolve_permissions(db, permission_ids)

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await role_repository.update(db, role, changes)
    audit_users = await user_repository.get_audit_info_map(db, {role.created_by, role.updated_by})
    return SingleResponse(data=_to_detail(role, audit_users))
