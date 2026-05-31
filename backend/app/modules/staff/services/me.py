"""
Self-service `/me` del doctor logueado (F3). Módulo de funciones.

Cada función resuelve el `Doctor` desde `CurrentAuth.user.id` (vía
`doctor_repository.get_by_user_id`) y delega en la MISMA lógica que el path
admin pasándole el `doctor.id` resuelto — el contrato (shapes, invariantes,
errores) es idéntico; solo cambia el permiso (router) y la resolución implícita
del doctor. Si el user logueado no tiene perfil de doctor → `403 NOT_A_DOCTOR`.

`update_my_doctor` usa `DoctorSelfUpdate` (solo bio/photo/signature/slot): el
doctor NO puede reasignarse sedes/verticales ni activarse — eso es del admin.
"""

from __future__ import annotations

from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthContext
from app.core.exceptions import ForbiddenException
from app.modules.staff.models.doctor import Doctor
from app.modules.staff.repositories.doctor import doctor_repository
from app.modules.staff.schemas.doctor import DoctorDetail, DoctorSelfUpdate, DoctorUpdate
from app.modules.staff.schemas.doctor_availability import (
    DoctorAvailabilityBulkCreate,
    DoctorAvailabilityItem,
    DoctorAvailabilityUpdate,
)
from app.modules.staff.services import doctor as doctor_service
from app.modules.staff.services import doctor_availability as availability_service
from app.shared.base_schemas import SingleResponse


async def _require_my_doctor(db: AsyncSession, auth: AuthContext) -> Doctor:
    doctor = await doctor_repository.get_by_user_id(db, auth.user.id)
    if doctor is None:
        raise ForbiddenException("Tu usuario no tiene un perfil de doctor", code="NOT_A_DOCTOR")
    return doctor


# ── Perfil ────────────────────────────────────────


async def get_my_doctor(db: AsyncSession, auth: AuthContext) -> SingleResponse[DoctorDetail]:
    doctor = await _require_my_doctor(db, auth)
    return await doctor_service.get_by_id(db, doctor.id)


async def update_my_doctor(
    db: AsyncSession, auth: AuthContext, payload: DoctorSelfUpdate
) -> SingleResponse[DoctorDetail]:
    doctor = await _require_my_doctor(db, auth)
    # Reusar el update admin con un DoctorUpdate que SOLO trae los campos propios
    # (exclude_unset preserva la semántica "solo lo enviado"); branch_ids/
    # vertical_ids/active quedan unset → el service no los toca.
    admin_payload = DoctorUpdate(**payload.model_dump(exclude_unset=True))
    return await doctor_service.update(db, doctor.id, admin_payload, actor_id=auth.id)


# ── Disponibilidad ────────────────────────────────


async def list_my_availability(
    db: AsyncSession,
    auth: AuthContext,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    doctor = await _require_my_doctor(db, auth)
    return await availability_service.list_for_doctor(db, doctor.id, date_from, date_to)


async def create_my_availability(
    db: AsyncSession, auth: AuthContext, payload: DoctorAvailabilityBulkCreate
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    doctor = await _require_my_doctor(db, auth)
    return await availability_service.bulk_create(db, doctor.id, payload, actor_id=auth.id)


async def update_my_availability(
    db: AsyncSession,
    auth: AuthContext,
    block_id: str,
    payload: DoctorAvailabilityUpdate,
) -> SingleResponse[DoctorAvailabilityItem]:
    doctor = await _require_my_doctor(db, auth)
    return await availability_service.update_block(
        db, doctor.id, block_id, payload, actor_id=auth.id
    )


async def delete_my_availability(db: AsyncSession, auth: AuthContext, block_id: str) -> None:
    doctor = await _require_my_doctor(db, auth)
    await availability_service.delete_block(db, doctor.id, block_id, actor_id=auth.id)
