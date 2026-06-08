"""
Lifecycle de citas (F3): la transición genérica valida la matriz (`is_allowed`,
ADR-008) y aplica los side-effects por code de destino (timestamps de columna); los
shortcuts (confirm/check-in/start/attend/no-show/cancel/reschedule) resuelven su
`to_status` por code y delegan en `transition`, sumando su lógica específica.

Los side-effects viven acá, NO en la matriz (ADR-008): la matriz solo dice si la
arista es válida. Codes en MAYÚSCULAS (espejan el seed F1: SCHEDULED/CONFIRMED/
CHECKED_IN/IN_PROGRESS/ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED).

`attend` promueve a cliente en la MISMA transacción (atómico): si no hay estado-cliente
inicial (NO_INITIAL_CUSTOMER_STATUS) la atención entera se revierte. `cancel` aplica el
invariante #9 (CANCEL_TOO_LATE) salvo permiso de override. `reschedule` crea una cita
NUEVA con `previous_appointment_id` y marca la vieja RESCHEDULED (misma tx).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthContext
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.modules.catalog.repositories.product import product_repository
from app.modules.crm.enums import ActivityType
from app.modules.crm.repositories.person_customer_status import (
    person_customer_status_repository,
)
from app.modules.crm.services import lead_activity as crm_lead_activity
from app.modules.crm.services import person_customer_status as crm_person_customer_status
from app.modules.scheduling.models.appointment import Appointment
from app.modules.scheduling.models.appointment_status_history import (
    AppointmentStatusHistory,
)
from app.modules.scheduling.repositories.appointment import appointment_repository
from app.modules.scheduling.repositories.appointment_status import (
    appointment_status_repository,
    appointment_status_transition_repository,
)
from app.modules.scheduling.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentDetail,
    AppointmentRescheduleRequest,
)
from app.modules.scheduling.services import availability as availability_service
from app.modules.scheduling.services.appointment import _to_detail
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _as_utc(dt: datetime) -> datetime:
    """sqlite (smoke) devuelve los timestamptz NAIVE; Postgres AWARE. Normaliza a la
    frontera para que el `scheduled_for - utc_now()` no explote (naive vs aware)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def transition(
    db: AsyncSession,
    appointment_id: str,
    to_status_id: str,
    *,
    actor_id: str,
    reason: str | None = None,
) -> SingleResponse[AppointmentDetail]:
    """Transición genérica: valida la matriz, escribe history, aplica el nuevo estado +
    side-effects por code. La fila SIGUE viva aunque el destino sea final (diverge de
    crm, donde is_final soft-deletea)."""
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    target = await appointment_status_repository.get_by_id(db, to_status_id)
    if target is None:
        raise NotFoundException("Estado no encontrado", code="APPOINTMENT_STATUS_NOT_FOUND")
    if not await appointment_status_transition_repository.is_allowed(
        db, appt.status_id, to_status_id
    ):
        current = await appointment_status_repository.get_by_id(db, appt.status_id)
        from_name = current.name if current is not None else appt.status_id
        raise BadRequestException(
            f"Transición de cita no permitida: de '{from_name}' a '{target.name}'",
            code="APPOINTMENT_TRANSITION_NOT_ALLOWED",
        )
    now = utc_now()
    from_id = appt.status_id
    db.add(
        AppointmentStatusHistory(
            id=generate_uuid(),
            appointment_id=appt.id,
            from_status_id=from_id,
            to_status_id=to_status_id,
            changed_at=now,
            changed_by=actor_id,
            reason=reason,
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
    )
    appt.status_id = to_status_id
    appt.updated_by = actor_id
    appt.updated_on = now
    # Side-effects por code del destino (timestamps de columna). cancellation_reason lo
    # setea `cancel` (necesita el payload); acá solo el timestamp + actor.
    if target.code == "CONFIRMED":
        appt.confirmed_at = now
    elif target.code == "CANCELLED":
        appt.cancelled_at = now
        appt.cancelled_by = actor_id
    elif target.code == "ATTENDED":
        appt.attended_at = now
    await db.flush()
    return SingleResponse(data=await _to_detail(db, appt))


async def _shortcut(
    db: AsyncSession,
    appointment_id: str,
    to_code: str,
    *,
    actor_id: str,
    reason: str | None = None,
) -> SingleResponse[AppointmentDetail]:
    target = await appointment_status_repository.get_by_code(db, to_code)
    if target is None:
        raise BadRequestException(
            f"Estado '{to_code}' no configurado", code="APPOINTMENT_STATUS_NOT_FOUND"
        )
    return await transition(db, appointment_id, target.id, actor_id=actor_id, reason=reason)


async def confirm(
    db: AsyncSession, appointment_id: str, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    return await _shortcut(db, appointment_id, "CONFIRMED", actor_id=actor_id)


async def check_in(
    db: AsyncSession, appointment_id: str, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    return await _shortcut(db, appointment_id, "CHECKED_IN", actor_id=actor_id)


async def start(
    db: AsyncSession, appointment_id: str, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    return await _shortcut(db, appointment_id, "IN_PROGRESS", actor_id=actor_id)


async def no_show(
    db: AsyncSession, appointment_id: str, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    return await _shortcut(db, appointment_id, "NO_SHOW", actor_id=actor_id)


async def attend(
    db: AsyncSession, appointment_id: str, *, actor_id: str
) -> SingleResponse[AppointmentDetail]:
    """ATTENDED + promote a cliente (atómico, misma tx) + LeadActivity. Si la persona ya
    es cliente → no-op CRM; si no hay estado-cliente inicial, `promote_from_lead` lanza
    NO_INITIAL_CUSTOMER_STATUS y NO se cachea → propaga y revierte toda la atención."""
    result = await _shortcut(db, appointment_id, "ATTENDED", actor_id=actor_id)
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:  # defensivo: el shortcut ya habría lanzado 404
        return result
    existing = await person_customer_status_repository.get_active_for_person(db, appt.person_id)
    if existing is None:
        try:
            await crm_person_customer_status.promote_from_lead(
                db, appt.person_id, actor_id=actor_id
            )
        except ConflictException:
            pass  # carrera ALREADY_CUSTOMER (entre el check y el promote) → no-op CRM
    # El vínculo cita↔actividad va por `related_appointment_id` (FK forward dedicada,
    # ADR-009) — única fuente, sin duplicarlo en el payload.
    await crm_lead_activity.log(
        db,
        appt.person_id,
        ActivityType.APPOINTMENT_ATTENDED,
        advisor_user_id=actor_id,
        actor_id=actor_id,
        content="Cita atendida",
        related_appointment_id=appt.id,
    )
    return result


async def cancel(
    db: AsyncSession,
    appointment_id: str,
    payload: AppointmentCancelRequest,
    *,
    actor: AuthContext,
) -> SingleResponse[AppointmentDetail]:
    """Cancela (→ CANCELLED). Invariante #9 CANCEL_TOO_LATE: si faltan menos de
    `product.min_hours_to_cancel` horas y el actor NO tiene APPOINTMENTS_CANCEL_OVERRIDE,
    400. Por eso recibe el AuthContext completo (necesita `actor.permissions`)."""
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    product = await product_repository.get_by_id(db, appt.product_id)
    min_hours = product.min_hours_to_cancel if product is not None else None
    if min_hours is not None:
        margin = _as_utc(appt.scheduled_for) - utc_now()
        if (
            margin < timedelta(hours=min_hours)
            and "APPOINTMENTS_CANCEL_OVERRIDE" not in actor.permissions
        ):
            raise BadRequestException(
                f"No se puede cancelar con menos de {min_hours} h de anticipación",
                code="CANCEL_TOO_LATE",
            )
    appt.cancellation_reason = payload.cancellation_reason
    return await _shortcut(
        db, appointment_id, "CANCELLED", actor_id=actor.id, reason=payload.cancellation_reason
    )


async def reschedule(
    db: AsyncSession,
    appointment_id: str,
    payload: AppointmentRescheduleRequest,
    *,
    actor_id: str,
) -> SingleResponse[AppointmentDetail]:
    """Marca la vieja RESCHEDULED + crea una cita NUEVA con `previous_appointment_id`
    (misma tx). Revalida los invariantes 1-8 sobre la nueva, EXCLUYENDO la vieja del
    conflicto. NO sujeto a min_hours_to_cancel (no es cancelación). Devuelve la NUEVA."""
    old = await appointment_repository.get_by_id(db, appointment_id)
    if old is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    new_doctor = payload.doctor_id or old.doctor_id
    new_office = payload.office_id or old.office_id
    # 1) Revalida invariantes sobre la NUEVA cita, excluyendo la vieja (que sigue viva en
    #    un estado bloqueante hasta marcarla) del chequeo de solape. for_update + advisory
    #    lock serializan contra reservas concurrentes.
    ctx = await availability_service.validate_booking_invariants(
        db,
        doctor_id=new_doctor,
        office_id=new_office,
        product_id=old.product_id,
        scheduled_for=payload.scheduled_for,
        exclude_id=old.id,
        for_update=True,
    )
    # 2) Marca la vieja RESCHEDULED (vía la matriz: scheduled/confirmed → rescheduled).
    rescheduled = await appointment_status_repository.get_by_code(db, "RESCHEDULED")
    if rescheduled is None:
        raise BadRequestException(
            "Estado 'RESCHEDULED' no configurado", code="APPOINTMENT_STATUS_NOT_FOUND"
        )
    if not await appointment_status_transition_repository.is_allowed(
        db, old.status_id, rescheduled.id
    ):
        raise BadRequestException(
            "No se puede reagendar desde este estado", code="APPOINTMENT_TRANSITION_NOT_ALLOWED"
        )
    await transition(
        db, old.id, rescheduled.id, actor_id=actor_id, reason=payload.reason or "Reagendada"
    )
    # 3) Crea la NUEVA cita en el is_initial, apuntando a la vieja (cadena acíclica).
    initial = await appointment_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException("No hay estado inicial configurado", code="NO_INITIAL_STATUS")
    now = utc_now()
    new = Appointment(
        id=generate_uuid(),
        person_id=old.person_id,
        doctor_id=new_doctor,
        office_id=new_office,
        branch_id=ctx.branch_id,
        product_id=old.product_id,
        scheduled_for=payload.scheduled_for,
        duration_min=ctx.duration_min,
        status_id=initial.id,
        source=old.source,
        previous_appointment_id=old.id,
        notes=old.notes,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(new)
    await db.flush()
    db.add(
        AppointmentStatusHistory(
            id=generate_uuid(),
            appointment_id=new.id,
            from_status_id=None,
            to_status_id=initial.id,
            changed_at=now,
            changed_by=actor_id,
            reason=f"Reagendada desde {old.id}",
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
    )
    await db.flush()
    return SingleResponse(data=await _to_detail(db, new))
