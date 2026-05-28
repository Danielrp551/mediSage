from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AlreadyExistsException,
    BadRequestException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import hash_password, verify_password
from app.modules.admin.models.user import User
from app.modules.admin.repositories.permission import permission_repository
from app.modules.admin.repositories.role import role_repository
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.admin.schemas.permission import PermissionOption
from app.modules.admin.schemas.role import RoleOption
from app.modules.admin.schemas.user import (
    PasswordChange,
    UserCreate,
    UserCreatedResponse,
    UserDetail,
    UserItem,
    UserUpdate,
)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_password, generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(user: User, audit_users: dict[str, User]) -> UserItem:
    return UserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        first_name=user.first_name,
        last_name=user.last_name,
        second_last_name=user.second_last_name,
        document_type=user.document_type,
        document_number=user.document_number,
        phone=user.phone,
        active=user.active,
        roles_count=len(user.roles),
        permissions_count=len(user.permissions),
        created_by=user.created_by,
        created_by_user=_audit_info(audit_users.get(user.created_by)),
        created_on=user.created_on,
        updated_by=user.updated_by,
        updated_by_user=_audit_info(audit_users.get(user.updated_by)),
        updated_on=user.updated_on,
    )


def _to_detail(user: User, audit_users: dict[str, User]) -> UserDetail:
    return UserDetail(
        **_to_item(user, audit_users).model_dump(),
        roles=[RoleOption.model_validate(r, from_attributes=True) for r in user.roles],
        permissions=[
            PermissionOption.model_validate(p, from_attributes=True) for p in user.permissions
        ],
    )


def _collect_actor_ids(rows: list[User]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _resolve_roles(db: AsyncSession, role_ids: list[str]):
    if not role_ids:
        return []
    roles = await role_repository.get_by_ids(db, role_ids)
    if len(roles) != len(set(role_ids)):
        found = {r.id for r in roles}
        missing = sorted(set(role_ids) - found)
        raise BadRequestException(f"Unknown role(s): {', '.join(missing)}")
    return roles


async def _resolve_permissions(db: AsyncSession, permission_ids: list[str]):
    if not permission_ids:
        return []
    perms = await permission_repository.get_by_ids(db, permission_ids)
    if len(perms) != len(set(permission_ids)):
        found = {p.id for p in perms}
        missing = sorted(set(permission_ids) - found)
        raise BadRequestException(f"Unknown permission(s): {', '.join(missing)}")
    return perms


# ── Reads ─────────────────────────────────────────


async def get_by_id(db: AsyncSession, user_id: str) -> SingleResponse[UserDetail]:
    user = await user_repository.get_full(db, user_id)
    if user is None:
        raise NotFoundException("User not found")
    audit_users = await user_repository.get_audit_info_map(db, {user.created_by, user.updated_by})
    return SingleResponse(data=_to_detail(user, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[UserItem]:
    items, total = await user_repository.get_paginated(
        db,
        query_request,
        load=(selectinload(User.roles), selectinload(User.permissions)),
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(u, audit_users) for u in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


# ── Writes ────────────────────────────────────────


async def create(
    db: AsyncSession,
    payload: UserCreate,
    *,
    actor_id: str,
) -> UserCreatedResponse:
    existing = await user_repository.get_by_email(db, payload.email)
    if existing is not None:
        raise AlreadyExistsException(f"Email '{payload.email}' is already registered")

    roles = await _resolve_roles(db, payload.role_ids)
    permissions = await _resolve_permissions(db, payload.permission_ids)

    plain = payload.password or generate_password()
    now = utc_now()
    user = User(
        id=generate_uuid(),
        email=payload.email,
        password_hash=hash_password(plain),
        first_name=payload.first_name,
        last_name=payload.last_name,
        second_last_name=payload.second_last_name,
        document_type=payload.document_type,
        document_number=payload.document_number,
        phone=payload.phone,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        roles=roles,
        permissions=permissions,
    )
    await user_repository.create(db, user)

    audit_users = await user_repository.get_audit_info_map(db, {user.created_by, user.updated_by})
    return UserCreatedResponse(
        data=_to_detail(user, audit_users),
        generated_password=plain if payload.password is None else None,
    )


async def update(
    db: AsyncSession,
    user_id: str,
    payload: UserUpdate,
    *,
    actor_id: str,
) -> SingleResponse[UserDetail]:
    user = await user_repository.get_full(db, user_id)
    if user is None:
        raise NotFoundException("User not found")

    changes = payload.model_dump(exclude_unset=True)
    role_ids = changes.pop("role_ids", None)
    permission_ids = changes.pop("permission_ids", None)

    if "email" in changes and changes["email"] != user.email:
        clash = await user_repository.get_by_email(db, changes["email"])
        if clash is not None:
            raise AlreadyExistsException(f"Email '{changes['email']}' is already registered")

    if role_ids is not None:
        user.roles = await _resolve_roles(db, role_ids)
    if permission_ids is not None:
        user.permissions = await _resolve_permissions(db, permission_ids)

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await user_repository.update(db, user, changes)

    audit_users = await user_repository.get_audit_info_map(db, {user.created_by, user.updated_by})
    return SingleResponse(data=_to_detail(user, audit_users))


async def change_password(
    db: AsyncSession,
    user: User,
    payload: PasswordChange,
) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise UnauthorizedException("Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.updated_on = utc_now()
    user.updated_by = user.id
    await db.flush()
