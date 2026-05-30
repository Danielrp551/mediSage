"""
Doctor service. Módulo de funciones (no clases), por convención del template.
Hidrata audit users (`created_by_user`/`updated_by_user`), el `full_name`/`email`
denormalizados del User 1:1 y los conteos de sedes/verticales en cada Item, más
el User resuelto + los M:N (branches/verticals) en cada Detail.

Creación NESTED (ADR-002): crea el `User` (asignándole el rol DOCTOR) Y el
`Doctor` en una sola transacción; devuelve `generated_password` si no se pasó uno
(mismo contrato que admin.user.create). Los M:N se resuelven con
`_resolve_branches`/`_resolve_verticals` (mirror de admin `_resolve_roles`):
`*_repository.get_by_ids` filtra soft-deleted, así que adjuntar una sede/vertical
muerta es un 400. Los paths de detalle recargan vía `doctor_repository.get_full`
(User + M:N eager, soft-deleted filtrados) — `create()`/`update()` solo refrescan
columnas y dejan las relaciones `lazy="raise"` sin cargar.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyExistsException,
    BadRequestException,
    NotFoundException,
)
from app.core.security import hash_password
from app.modules.admin.models.role import Role
from app.modules.admin.models.user import User
from app.modules.admin.repositories.role import role_repository
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.models.vertical import Vertical
from app.modules.catalog.repositories.vertical import vertical_repository
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.repositories.branch import branch_repository
from app.modules.clinic.schemas.branch import BranchOption
from app.modules.staff.models.doctor import Doctor
from app.modules.staff.repositories.doctor import doctor_repository
from app.modules.staff.schemas.doctor import (
    DoctorCreate,
    DoctorCreatedResponse,
    DoctorDetail,
    DoctorItem,
    DoctorOption,
    DoctorUpdate,
)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_password, generate_uuid, utc_now

DOCTOR_ROLE_NAME = "DOCTOR"


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(
    doctor: Doctor,
    audit_users: dict[str, User],
    *,
    full_name: str,
    email: str,
    branches_count: int = 0,
    verticals_count: int = 0,
) -> DoctorItem:
    return DoctorItem(
        id=doctor.id,
        user_id=doctor.user_id,
        full_name=full_name,
        email=email,
        cmp_code=doctor.cmp_code,
        slot_duration_min=doctor.slot_duration_min,
        active=doctor.active,
        branches_count=branches_count,
        verticals_count=verticals_count,
        created_on=doctor.created_on,
        created_by=doctor.created_by,
        created_by_user=_audit_info(audit_users.get(doctor.created_by)),
        updated_on=doctor.updated_on,
        updated_by=doctor.updated_by,
        updated_by_user=_audit_info(audit_users.get(doctor.updated_by)),
    )


def _to_detail(doctor: Doctor, audit_users: dict[str, User]) -> DoctorDetail:
    # `doctor.user`, `doctor.branches` y `doctor.verticals` deben venir eager
    # (get_full) — son `lazy="raise"`. branches/verticals ya filtran soft-deleted
    # por el with_loader_criteria de get_full.
    return DoctorDetail(
        **_to_item(
            doctor,
            audit_users,
            full_name=doctor.user.full_name,
            email=doctor.user.email,
            branches_count=len(doctor.branches),
            verticals_count=len(doctor.verticals),
        ).model_dump(),
        bio=doctor.bio,
        photo_url=doctor.photo_url,
        signature_url=doctor.signature_url,
        user=UserAuditInfo(
            id=doctor.user.id, full_name=doctor.user.full_name, email=doctor.user.email
        ),
        branches=[BranchOption.model_validate(b, from_attributes=True) for b in doctor.branches],
        verticals=[
            VerticalOption.model_validate(v, from_attributes=True) for v in doctor.verticals
        ],
    )


def _collect_actor_ids(rows: list[Doctor]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def _resolve_branches(db: AsyncSession, branch_ids: list[str]) -> list[Branch]:
    if not branch_ids:
        return []
    branches = await branch_repository.get_by_ids(db, branch_ids)
    if len(branches) != len(set(branch_ids)):
        found = {b.id for b in branches}
        missing = sorted(set(branch_ids) - found)
        raise BadRequestException(
            f"Sede(s) no encontrada(s): {', '.join(missing)}", code="BRANCH_NOT_FOUND"
        )
    return branches


async def _resolve_verticals(db: AsyncSession, vertical_ids: list[str]) -> list[Vertical]:
    if not vertical_ids:
        return []
    verticals = await vertical_repository.get_by_ids(db, vertical_ids)
    if len(verticals) != len(set(vertical_ids)):
        found = {v.id for v in verticals}
        missing = sorted(set(vertical_ids) - found)
        raise BadRequestException(
            f"Vertical(es) no encontrada(s): {', '.join(missing)}", code="VERTICAL_NOT_FOUND"
        )
    return verticals


async def _get_doctor_role(db: AsyncSession) -> Role:
    role = await role_repository.get_by_name(db, DOCTOR_ROLE_NAME)
    if role is None:
        # Invariante de seed: el rol DOCTOR siempre existe (F0). Si falta, es un
        # error de configuración — fallar claro en vez de crear un user sin rol.
        raise BadRequestException(
            "El rol DOCTOR no está configurado en el sistema", code="DOCTOR_ROLE_MISSING"
        )
    return role


async def list_active(
    db: AsyncSession, branch_id: str | None = None, vertical_id: str | None = None
) -> list[DoctorOption]:
    """Lista doctores activos para dropdowns, opcionalmente acotada por sede y/o
    vertical. Devuelve la lista cruda (sin envelope), consistente con el módulo."""
    rows = await doctor_repository.list_active(db, branch_id=branch_id, vertical_id=vertical_id)
    options = [DoctorOption(id=d.id, full_name=d.user.full_name, cmp_code=d.cmp_code) for d in rows]
    options.sort(key=lambda o: o.full_name.lower())
    return options


async def get_by_id(db: AsyncSession, doctor_id: str) -> SingleResponse[DoctorDetail]:
    doctor = await doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(
        db, {doctor.created_by, doctor.updated_by}
    )
    return SingleResponse(data=_to_detail(doctor, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[DoctorItem]:
    items, total = await doctor_repository.get_paginated(db, query_request)
    doctor_ids = [d.id for d in items]
    # Un solo lookup de users cubre tanto a los doctores (full_name/email) como a
    # los actores de auditoría; dos conteos batch para los M:N. Sin N+1.
    user_ids = {d.user_id for d in items} | _collect_actor_ids(items)
    users = await user_repository.get_audit_info_map(db, user_ids)
    bcounts = await doctor_repository.count_branches_map(db, doctor_ids)
    vcounts = await doctor_repository.count_verticals_map(db, doctor_ids)
    rows: list[DoctorItem] = []
    for d in items:
        du = users.get(d.user_id)
        rows.append(
            _to_item(
                d,
                users,
                full_name=du.full_name if du else "",
                email=du.email if du else "desconocido@desconocido.local",
                branches_count=bcounts.get(d.id, 0),
                verticals_count=vcounts.get(d.id, 0),
            )
        )
    return PaginatedResponse(
        data=PaginatedData(
            items=rows,
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: DoctorCreate, *, actor_id: str
) -> DoctorCreatedResponse:
    # 1) Validar todo ANTES de insertar (email único + rol + M:N).
    existing = await user_repository.get_by_email(db, payload.user.email)
    if existing is not None:
        raise AlreadyExistsException(
            f"El correo '{payload.user.email}' ya está registrado", code="EMAIL_TAKEN"
        )
    doctor_role = await _get_doctor_role(db)
    branches = await _resolve_branches(db, payload.branch_ids)
    verticals = await _resolve_verticals(db, payload.vertical_ids)

    # 2) Crear User (con rol DOCTOR) + Doctor en la misma transacción.
    plain = payload.user.password or generate_password()
    now = utc_now()
    user = User(
        id=generate_uuid(),
        email=payload.user.email,
        password_hash=hash_password(plain),
        first_name=payload.user.first_name,
        last_name=payload.user.last_name,
        second_last_name=payload.user.second_last_name,
        document_type=payload.user.document_type,
        document_number=payload.user.document_number,
        phone=payload.user.phone,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        roles=[doctor_role],
    )
    await user_repository.create(db, user)

    doctor = Doctor(
        id=generate_uuid(),
        user_id=user.id,
        cmp_code=payload.cmp_code,
        bio=payload.bio,
        photo_url=payload.photo_url,
        signature_url=payload.signature_url,
        slot_duration_min=payload.slot_duration_min,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        branches=branches,
        verticals=verticals,
    )
    await doctor_repository.create(db, doctor)

    # 3) Recargar con User + M:N eager (create solo refresca columnas).
    created = await doctor_repository.get_full(db, doctor.id)
    if created is None:  # pragma: no cover - recién insertado, no puede faltar
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(
        db, {created.created_by, created.updated_by}
    )
    return DoctorCreatedResponse(
        data=_to_detail(created, audit_users),
        generated_password=plain if payload.user.password is None else None,
    )


async def update(
    db: AsyncSession,
    doctor_id: str,
    payload: DoctorUpdate,
    *,
    actor_id: str,
) -> SingleResponse[DoctorDetail]:
    doctor = await doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    branch_ids = changes.pop("branch_ids", None)
    vertical_ids = changes.pop("vertical_ids", None)

    # Reemplazo total del M:N solo cuando el campo viene en el payload.
    if branch_ids is not None:
        doctor.branches = await _resolve_branches(db, branch_ids)
    if vertical_ids is not None:
        doctor.verticals = await _resolve_verticals(db, vertical_ids)

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await doctor_repository.update(db, doctor, changes)

    refreshed = await doctor_repository.get_full(db, doctor_id)
    if refreshed is None:  # pragma: no cover - recién actualizado, no puede faltar
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(
        db, {refreshed.created_by, refreshed.updated_by}
    )
    return SingleResponse(data=_to_detail(refreshed, audit_users))


async def soft_delete(db: AsyncSession, doctor_id: str, *, actor_id: str) -> None:
    doctor = await doctor_repository.get_by_id(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    # ADR-002: el soft-delete del Doctor NO toca al User. Para bloquear el acceso
    # del doctor a la plataforma se pone user.active=false desde el módulo admin.
    doctor.updated_by = actor_id
    doctor.updated_on = utc_now()
    await doctor_repository.soft_delete(db, doctor)
