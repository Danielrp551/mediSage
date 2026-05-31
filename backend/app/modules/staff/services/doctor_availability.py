"""
DoctorAvailability service. Módulo de funciones (no clases).

Bloques concretos por fecha (ADR-007). Tres invariantes cross-tabla, validados en
el service (no como CHECK), cada uno con su `code`:
  1. `OFFICE_NOT_IN_BRANCH`  — el office pertenece al branch indicado.
  2. `DOCTOR_NOT_IN_BRANCH`  — el doctor está asignado a ese branch (doctor_branch).
  3. `AVAILABILITY_OVERLAP`  — dos bloques del mismo doctor en la misma fecha no se
     solapan en `[opens_at, closes_at)` (half-open; adyacentes OK).
Se validan en el POST bulk (cada bloque entrante + los del propio body entre sí) y
en el PUT (bloque mergeado, excluyéndose a sí mismo del chequeo de solape).

El invariante 4 ("el bloque cabe en OfficeOperatingHours") NO se valida acá —
scheduling intersecta el bloque con el horario del office, así que la porción
fuera de horario simplemente no genera slots.

`_to_items` denormaliza branch_name / office_code / office_name vía lookups batch
(el bloque no tiene relación ORM a branch/office, solo `doctor`).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.clinic.repositories.office import office_repository
from app.modules.staff.models.doctor import Doctor
from app.modules.staff.models.doctor_availability import DoctorAvailability
from app.modules.staff.repositories.doctor import doctor_repository
from app.modules.staff.repositories.doctor_availability import doctor_availability_repository
from app.modules.staff.schemas.doctor_availability import (
    DoctorAvailabilityBulkCreate,
    DoctorAvailabilityItem,
    DoctorAvailabilityUpdate,
)
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


async def _to_items(
    db: AsyncSession, blocks: list[DoctorAvailability]
) -> list[DoctorAvailabilityItem]:
    """Construye los Item denormalizando branch_name/office_code/office_name +
    los audit users, todo en lookups batch (sin N+1)."""
    if not blocks:
        return []
    branch_names = await doctor_availability_repository.branch_name_map(
        db, [b.branch_id for b in blocks]
    )
    offices = await doctor_availability_repository.office_map(db, [b.office_id for b in blocks])
    actor_ids: set[str] = set()
    for b in blocks:
        actor_ids.add(b.created_by)
        actor_ids.add(b.updated_by)
    audit_users = await user_repository.get_audit_info_map(db, actor_ids)

    items: list[DoctorAvailabilityItem] = []
    for b in blocks:
        office_code, office_name = offices.get(b.office_id, ("", ""))
        items.append(
            DoctorAvailabilityItem(
                id=b.id,
                doctor_id=b.doctor_id,
                branch_id=b.branch_id,
                branch_name=branch_names.get(b.branch_id, ""),
                office_id=b.office_id,
                office_code=office_code,
                office_name=office_name,
                date=b.date,
                opens_at=b.opens_at,
                closes_at=b.closes_at,
                active=b.active,
                created_on=b.created_on,
                created_by=b.created_by,
                created_by_user=_audit_info(audit_users.get(b.created_by)),
                updated_on=b.updated_on,
                updated_by=b.updated_by,
                updated_by_user=_audit_info(audit_users.get(b.updated_by)),
            )
        )
    return items


async def _require_doctor(db: AsyncSession, doctor_id: str) -> Doctor:
    # get_full carga branches (necesario para el invariante 2).
    doctor = await doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    return doctor


async def _validate_block(
    db: AsyncSession,
    doctor: Doctor,
    branch_id: str,
    office_id: str,
    on_date: date_type,
    opens_at: time,
    closes_at: time,
    *,
    existing_same_date: list[DoctorAvailability],
    exclude_block_id: str | None = None,
) -> None:
    # Invariante 1: el office pertenece al branch.
    office = await office_repository.get_by_id(db, office_id)
    if office is None or office.branch_id != branch_id:
        raise BadRequestException(
            "El consultorio no pertenece a la sede indicada", code="OFFICE_NOT_IN_BRANCH"
        )
    # Invariante 2: el doctor está asignado a ese branch (doctor_branch).
    if branch_id not in {b.id for b in doctor.branches}:
        raise BadRequestException(
            "El doctor no está asignado a esta sede", code="DOCTOR_NOT_IN_BRANCH"
        )
    # Invariante 3: no-solape con otros bloques del MISMO doctor en la MISMA fecha.
    #   Half-open [opens, closes): adyacentes OK ([08-13) y [13-20) no se solapan).
    for other in existing_same_date:
        if exclude_block_id is not None and other.id == exclude_block_id:
            continue
        if opens_at < other.closes_at and other.opens_at < closes_at:
            raise BadRequestException(
                f"El bloque se solapa con otra disponibilidad del doctor el {on_date.isoformat()}",
                code="AVAILABILITY_OVERLAP",
            )


async def list_for_doctor(
    db: AsyncSession,
    doctor_id: str,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    # El doctor debe existir (404) antes de listar.
    await _require_doctor(db, doctor_id)
    blocks = await doctor_availability_repository.list_for_doctor(db, doctor_id, date_from, date_to)
    return SingleResponse(data=await _to_items(db, blocks))


async def bulk_create(
    db: AsyncSession,
    doctor_id: str,
    payload: DoctorAvailabilityBulkCreate,
    *,
    actor_id: str,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    doctor = await _require_doctor(db, doctor_id)

    now = utc_now()
    created: list[DoctorAvailability] = []
    # Acumulador por fecha: bloques vivos existentes + los ya agregados en ESTE
    # body, para que dos bloques del body en la misma fecha se chequeen entre sí.
    by_date: dict[date_type, list[DoctorAvailability]] = {}
    for block in payload.blocks:
        if block.date not in by_date:
            by_date[block.date] = await doctor_availability_repository.list_for_doctor_on_date(
                db, doctor_id, block.date
            )
        await _validate_block(
            db,
            doctor,
            block.branch_id,
            block.office_id,
            block.date,
            block.opens_at,
            block.closes_at,
            existing_same_date=by_date[block.date],
        )
        row = DoctorAvailability(
            id=generate_uuid(),
            doctor_id=doctor_id,
            branch_id=block.branch_id,
            office_id=block.office_id,
            date=block.date,
            opens_at=block.opens_at,
            closes_at=block.closes_at,
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
        db.add(row)
        by_date[block.date].append(row)  # los bloques siguientes del body lo ven
        created.append(row)
    await db.flush()
    return SingleResponse(data=await _to_items(db, created))


async def update_block(
    db: AsyncSession,
    doctor_id: str,
    block_id: str,
    payload: DoctorAvailabilityUpdate,
    *,
    actor_id: str,
) -> SingleResponse[DoctorAvailabilityItem]:
    doctor = await _require_doctor(db, doctor_id)
    block = await doctor_availability_repository.get_by_id(db, block_id)
    # Ownership: el bloque debe existir Y pertenecer a este doctor.
    if block is None or block.doctor_id != doctor_id:
        raise NotFoundException("Disponibilidad no encontrada", code="AVAILABILITY_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    merged_branch = changes.get("branch_id", block.branch_id)
    merged_office = changes.get("office_id", block.office_id)
    merged_date = changes.get("date", block.date)
    merged_opens = changes.get("opens_at", block.opens_at)
    merged_closes = changes.get("closes_at", block.closes_at)
    if merged_closes <= merged_opens:
        # Convención del módulo: detail en español + code en inglés. Este path es
        # alcanzable cuando el PUT setea solo un lado del intervalo (el validator
        # cross-field de Pydantic solo corre si vienen ambos en el body).
        raise BadRequestException(
            "La hora de cierre debe ser posterior a la de apertura",
            code="AVAILABILITY_INVALID_RANGE",
        )

    same_date = await doctor_availability_repository.list_for_doctor_on_date(
        db, doctor_id, merged_date
    )
    await _validate_block(
        db,
        doctor,
        merged_branch,
        merged_office,
        merged_date,
        merged_opens,
        merged_closes,
        existing_same_date=same_date,
        exclude_block_id=block_id,
    )
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await doctor_availability_repository.update(db, block, changes)
    items = await _to_items(db, [block])
    return SingleResponse(data=items[0])


async def delete_block(db: AsyncSession, doctor_id: str, block_id: str, *, actor_id: str) -> None:
    await _require_doctor(db, doctor_id)
    block = await doctor_availability_repository.get_by_id(db, block_id)
    if block is None or block.doctor_id != doctor_id:
        raise NotFoundException("Disponibilidad no encontrada", code="AVAILABILITY_NOT_FOUND")
    block.updated_by = actor_id
    block.updated_on = utc_now()
    await doctor_availability_repository.soft_delete(db, block)
