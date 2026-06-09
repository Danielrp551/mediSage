"""
Appointment service (F2): create/book (9 invariantes + SELECT FOR UPDATE → SLOT_TAKEN),
list paginado, get detalle, y `/me` (agenda del doctor logueado, scoped). Denormaliza
person/doctor/office/branch/product + badge de estado vía batch maps (sin N+1).

Scoping (per backend.md): `/appointments/list` y `/appointments/{id}` requieren
APPOINTMENTS_READ → ven TODAS las citas (la permission es el gate). `/me/appointments/list`
(MY_APPOINTMENTS_READ) fuerza `doctor_id == doctor del user` (override de cualquier filtro
del cliente → sin IDOR); si el user no tiene perfil Doctor, devuelve página vacía.

El update (PUT, changelog), las transiciones y el calendario llegan en fases siguientes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.marketing.services import promotion_usage as marketing_promotion_usage
from app.modules.scheduling.models.appointment import Appointment
from app.modules.scheduling.models.appointment_change_log import AppointmentChangeLog
from app.modules.scheduling.models.appointment_status import AppointmentStatus
from app.modules.scheduling.models.appointment_status_history import (
    AppointmentStatusHistory,
)
from app.modules.scheduling.repositories.appointment import appointment_repository
from app.modules.scheduling.repositories.appointment_change_log import (
    appointment_change_log_repository,
)
from app.modules.scheduling.repositories.appointment_status import (
    appointment_status_repository,
)
from app.modules.scheduling.repositories.appointment_status_history import (
    appointment_status_history_repository,
)
from app.modules.scheduling.schemas.appointment import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentItem,
    AppointmentUpdate,
)
from app.modules.scheduling.schemas.appointment_status import AppointmentStatusOption
from app.modules.scheduling.schemas.audit import (
    AppointmentChangeLogItem,
    AppointmentStatusHistoryItem,
)
from app.modules.scheduling.services import availability as availability_service
from app.modules.staff.repositories.doctor import doctor_repository
from app.shared.base_schemas import (
    FilterCondition,
    FilterGroup,
    FilterOperator,
    FilterParams,
    GroupOperator,
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now


def _audit_info(user: User | None) -> UserAuditInfo | None:
    if user is None:
        return None
    return UserAuditInfo(id=user.id, full_name=user.full_name, email=user.email)


def _badge(status: AppointmentStatus | None) -> AppointmentStatusOption | None:
    if status is None:
        return None
    return AppointmentStatusOption.model_validate(status, from_attributes=True)


def _force_filter(query: QueryRequest, field: str, value: str) -> QueryRequest:
    """Agrega un grupo AND que fuerza `field == value` (los grupos se combinan con AND
    → el cliente no puede ampliar el scope). Para el /me anti-IDOR."""
    forced = FilterGroup(
        operator=GroupOperator.AND,
        conditions=[FilterCondition(field=field, operator=FilterOperator.EQ, value=value)],
    )
    existing = query.filters.filters if query.filters else []
    return query.model_copy(update={"filters": FilterParams(filters=[*existing, forced])})


class _Maps:
    """Batch maps para denormalizar una lista de citas sin N+1."""

    def __init__(self) -> None:
        self.person: dict[str, str] = {}
        self.doctor: dict[str, str] = {}
        self.office: dict[str, tuple[str, str]] = {}
        self.branch: dict[str, str] = {}
        self.product: dict[str, str] = {}
        self.status: dict[str, AppointmentStatus] = {}
        self.users: dict[str, User] = {}


async def _build_maps(
    db: AsyncSession, appts: list[Appointment], *, extra_user_ids: set[str] | None = None
) -> _Maps:
    maps = _Maps()
    if not appts:
        return maps
    person_ids = list({a.person_id for a in appts})
    doctor_ids = list({a.doctor_id for a in appts})
    office_ids = list({a.office_id for a in appts})
    branch_ids = list({a.branch_id for a in appts})
    product_ids = list({a.product_id for a in appts})
    status_ids = list({a.status_id for a in appts})

    maps.person = await appointment_repository.person_name_map(db, person_ids)
    maps.doctor = await appointment_repository.doctor_name_map(db, doctor_ids)
    maps.office = await appointment_repository.office_map(db, office_ids)
    maps.branch = await appointment_repository.branch_name_map(db, branch_ids)
    maps.product = await appointment_repository.product_name_map(db, product_ids)
    # Badge tolerante a soft-deleted (un estado borrado no debe 500-ear la lectura).
    maps.status = {
        s.id: s for s in await appointment_status_repository.get_by_ids_for_badge(db, status_ids)
    }

    user_ids: set[str] = set(extra_user_ids or set())
    for a in appts:
        user_ids.add(a.created_by)
        user_ids.add(a.updated_by)
    maps.users = await user_repository.get_audit_info_map(db, user_ids)
    return maps


def _to_item(appt: Appointment, maps: _Maps) -> AppointmentItem:
    office_name, _ = maps.office.get(appt.office_id, ("", appt.branch_id))
    status = _badge(maps.status.get(appt.status_id))
    assert status is not None  # toda cita viva tiene un estado del catálogo
    return AppointmentItem(
        id=appt.id,
        person_id=appt.person_id,
        person_name=maps.person.get(appt.person_id, ""),
        doctor_id=appt.doctor_id,
        doctor_name=maps.doctor.get(appt.doctor_id, ""),
        office_id=appt.office_id,
        office_name=office_name,
        branch_id=appt.branch_id,
        branch_name=maps.branch.get(appt.branch_id, ""),
        product_id=appt.product_id,
        product_name=maps.product.get(appt.product_id, ""),
        scheduled_for=appt.scheduled_for,
        duration_min=appt.duration_min,
        status=status,
        source=appt.source,
        previous_appointment_id=appt.previous_appointment_id,
        active=appt.active,
        created_on=appt.created_on,
        created_by=appt.created_by,
        created_by_user=_audit_info(maps.users.get(appt.created_by)),
        updated_on=appt.updated_on,
        updated_by=appt.updated_by,
        updated_by_user=_audit_info(maps.users.get(appt.updated_by)),
    )


async def _to_detail(db: AsyncSession, appt: Appointment) -> AppointmentDetail:
    history = await appointment_status_history_repository.list_for_appointment(db, appt.id)
    changes = await appointment_change_log_repository.list_for_appointment(db, appt.id)

    # Maps: la cita + los estados from/to del history + los users changed_by.
    hist_status_ids = {h.to_status_id for h in history} | {
        h.from_status_id for h in history if h.from_status_id is not None
    }
    extra_user_ids = {h.changed_by for h in history if h.changed_by} | {
        c.changed_by for c in changes if c.changed_by
    }
    maps = await _build_maps(db, [appt], extra_user_ids=extra_user_ids)
    # Completar los estados del history que no estén ya en el badge map.
    missing = list(hist_status_ids - set(maps.status))
    if missing:
        for s in await appointment_status_repository.get_by_ids_for_badge(db, missing):
            maps.status[s.id] = s

    item = _to_item(appt, maps)
    history_items = [
        AppointmentStatusHistoryItem(
            id=h.id,
            appointment_id=h.appointment_id,
            from_status=_badge(maps.status.get(h.from_status_id)) if h.from_status_id else None,
            to_status=_badge(maps.status.get(h.to_status_id)),
            changed_at=h.changed_at,
            changed_by=h.changed_by,
            changed_by_user=_audit_info(maps.users.get(h.changed_by)) if h.changed_by else None,
            reason=h.reason,
        )
        for h in history
    ]
    change_items = [
        AppointmentChangeLogItem(
            id=c.id,
            appointment_id=c.appointment_id,
            field_name=c.field_name,
            previous_value=c.previous_value,
            new_value=c.new_value,
            changed_at=c.changed_at,
            changed_by=c.changed_by,
            changed_by_user=_audit_info(maps.users.get(c.changed_by)) if c.changed_by else None,
            reason=c.reason,
        )
        for c in changes
    ]
    return AppointmentDetail(
        **item.model_dump(),
        notes=appt.notes,
        cancellation_reason=appt.cancellation_reason,
        cancelled_at=appt.cancelled_at,
        cancelled_by=appt.cancelled_by,
        confirmed_at=appt.confirmed_at,
        attended_at=appt.attended_at,
        status_history=history_items,
        change_log=change_items,
    )


# ── Operaciones ───────────────────────────────────────────────────────


async def create_appointment(
    db: AsyncSession, payload: AppointmentCreate, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    ctx = await availability_service.validate_booking_invariants(
        db,
        doctor_id=payload.doctor_id,
        office_id=payload.office_id,
        product_id=payload.product_id,
        scheduled_for=payload.scheduled_for,
        exclude_id=None,
        for_update=True,  # FOR UPDATE sobre citas solapantes + advisory lock por doctor/office
    )
    initial = await appointment_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException("No hay estado inicial configurado", code="NO_INITIAL_STATUS")

    now = utc_now()
    appt = Appointment(
        id=generate_uuid(),
        person_id=payload.person_id,
        doctor_id=payload.doctor_id,
        office_id=payload.office_id,
        branch_id=ctx.branch_id,
        product_id=payload.product_id,
        scheduled_for=payload.scheduled_for,
        duration_min=ctx.duration_min,
        status_id=initial.id,
        source=payload.source.value,
        previous_appointment_id=None,
        notes=payload.notes,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(appt)
    await db.flush()
    db.add(
        AppointmentStatusHistory(
            id=generate_uuid(),
            appointment_id=appt.id,
            from_status_id=None,
            to_status_id=initial.id,
            changed_at=now,
            changed_by=actor_id,
            reason="Cita agendada",
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
    )
    await db.flush()
    # F4 (marketing): aplicar la promo en la MISMA sesión (atómico, sin commit). Si la promo
    # es inválida (PROMOTION_* de dominio), la excepción propaga → el rollback global del
    # request revierte la cita Y el history (NO se persiste nada). NO se usa savepoint: ningún
    # except escribe sobre la sesión aquí (lección §15). Reschedule crea la cita nueva por otro
    # camino (transition.reschedule) → NO re-aplica la promo (queda en la cita vieja).
    if payload.apply_promotion_id:
        await marketing_promotion_usage.apply(
            db,
            promotion_id=payload.apply_promotion_id,
            person_id=payload.person_id,
            product_id=payload.product_id,
            appointment_id=appt.id,
            actor_id=actor_id,
        )
    return SingleResponse(data=await _to_detail(db, appt))


async def list_paginated(
    db: AsyncSession, query: QueryRequest
) -> PaginatedResponse[AppointmentItem]:
    items, total = await appointment_repository.get_paginated(db, query)
    maps = await _build_maps(db, items)
    rows = [_to_item(a, maps) for a in items]
    return PaginatedResponse(
        data=PaginatedData(
            items=rows, total=total, skip=query.pagination.skip, limit=query.pagination.limit
        )
    )


async def get_by_id(db: AsyncSession, appointment_id: str) -> SingleResponse[AppointmentDetail]:
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    return SingleResponse(data=await _to_detail(db, appt))


async def list_for_current_doctor(
    db: AsyncSession, query: QueryRequest, *, user_id: str
) -> PaginatedResponse[AppointmentItem]:
    """/me/appointments/list — fuerza doctor_id == doctor del user (anti-IDOR). Si el
    user no tiene perfil Doctor, devuelve página vacía."""
    doctor = await doctor_repository.get_by_user_id(db, user_id)
    if doctor is None:
        return PaginatedResponse(
            data=PaginatedData(
                items=[], total=0, skip=query.pagination.skip, limit=query.pagination.limit
            )
        )
    scoped = _force_filter(query, "doctor_id", doctor.id)
    return await list_paginated(db, scoped)


async def update_appointment(
    db: AsyncSession, appointment_id: str, payload: AppointmentUpdate, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    """PUT /appointments/{id} (F3) — edita SOLO columnas no-estado/no-tiempo
    (doctor_id/office_id/product_id/notes). Cada cambio → una fila de AppointmentChangeLog.
    Si cambia doctor/office/product, revalida los invariantes 1-8 sobre el nuevo combo
    (sin tocar scheduled_for, excluyendo la propia cita del solape) y re-deriva
    branch_id/duration_min del producto/office. status_id y scheduled_for NO se editan
    acá (usan /transition y /reschedule)."""
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")

    new_doctor = payload.doctor_id if payload.doctor_id is not None else appt.doctor_id
    new_office = payload.office_id if payload.office_id is not None else appt.office_id
    new_product = payload.product_id if payload.product_id is not None else appt.product_id
    revalidate = (
        new_doctor != appt.doctor_id
        or new_office != appt.office_id
        or new_product != appt.product_id
    )
    # Revalidar ANTES de mutar la cita: si el nuevo combo es inválido (office no apto,
    # solape, …), la excepción propaga y la cita queda intacta.
    ctx = (
        await availability_service.validate_booking_invariants(
            db,
            doctor_id=new_doctor,
            office_id=new_office,
            product_id=new_product,
            scheduled_for=appt.scheduled_for,
            exclude_id=appt.id,
            for_update=True,
        )
        if revalidate
        else None
    )

    # Solo se registra (y aplica) un cambio si el valor llega y DIFIERE del actual.
    changes: list[tuple[str, str | None, str | None]] = []
    if payload.doctor_id is not None and payload.doctor_id != appt.doctor_id:
        changes.append(("doctor_id", appt.doctor_id, payload.doctor_id))
        appt.doctor_id = payload.doctor_id
    if payload.office_id is not None and payload.office_id != appt.office_id:
        changes.append(("office_id", appt.office_id, payload.office_id))
        appt.office_id = payload.office_id
    if payload.product_id is not None and payload.product_id != appt.product_id:
        changes.append(("product_id", appt.product_id, payload.product_id))
        appt.product_id = payload.product_id
    # notes es NULLABLE: a diferencia de los 3 FKs (NOT NULL → `is not None` distingue
    # "no enviado"), acá se usa `model_fields_set` (como crm.lead_activity.update con
    # exclude_unset) para distinguir "no enviado" de "enviado como null" → permite
    # LIMPIAR las notas (notes=null) sin confundirlo con "no cambiar".
    if "notes" in payload.model_fields_set and payload.notes != appt.notes:
        changes.append(("notes", appt.notes, payload.notes))
        appt.notes = payload.notes

    if ctx is not None:
        # branch_id/duration_min son consecuencias derivadas (no edición directa) → se
        # actualizan sin fila de changelog (el changelog registra los campos editados).
        appt.branch_id = ctx.branch_id
        appt.duration_min = ctx.duration_min

    if changes:
        now = utc_now()
        appt.updated_by = actor_id
        appt.updated_on = now
        for field_name, old_value, new_value in changes:
            db.add(
                AppointmentChangeLog(
                    id=generate_uuid(),
                    appointment_id=appt.id,
                    field_name=field_name,
                    previous_value=old_value,
                    new_value=new_value,
                    changed_at=now,
                    changed_by=actor_id,
                    reason=payload.reason,
                    active=True,
                    created_by=actor_id,
                    created_on=now,
                    updated_by=actor_id,
                    updated_on=now,
                )
            )
        await db.flush()
    return SingleResponse(data=await _to_detail(db, appt))


async def delete_appointment(db: AsyncSession, appointment_id: str, *, actor_id: str) -> None:
    """DELETE /appointments/{id} (F3) — soft delete SOLO para "error de captura" (admin).
    NO es el camino de cierre normal: una cita ATTENDED/CANCELLED/NO_SHOW mantiene su fila
    viva como registro histórico. Aquí se oculta una cita creada por error."""
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    appt.updated_by = actor_id
    appt.updated_on = utc_now()
    await appointment_repository.soft_delete(db, appt)
