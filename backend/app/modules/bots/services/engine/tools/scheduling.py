"""
Tools de scheduling (F5) — cierran el loop lead→bot→cita→cliente. El bot consulta
disponibilidad, reserva y cancela citas para el contacto del hilo. Corren como SYSTEM
(sin CurrentAuth): las reglas las imponen los services de scheduling (los 9 invariantes,
la matriz de transición, CANCEL_TOO_LATE). Reusan las firmas REALES verificadas:
- availability.compute_available_slots(db, *, doctor_id, product_id, branch_id=None,
    office_id=None, from_date, to_date) -> AvailabilityResponse
- appointment.create_appointment(db, AppointmentCreate, *, actor_id) -> SingleResponse[Detail]
- transition.cancel(db, appointment_id, AppointmentCancelRequest, *, actor: AuthContext)
    -> SingleResponse[Detail]   (necesita AuthContext por el check de override)

Patrón de error (igual que las tools de crm): se capturan las excepciones de DOMINIO
(BadRequest/Conflict/NotFound — que scheduling lanza ANTES de escribir, sesión limpia) y se
devuelven como result `{"ok": False, "error": code}` para que el LLM las vea y le explique al
usuario. Lo INESPERADO propaga al savepoint del engine (begin_nested por tool) — no se captura
en ancho para no comerse un error de BD con la sesión sucia (lección bots F3a).

El bot reserva SIEMPRE para `ctx.person_id` (el contacto del hilo), NUNCA para un id que venga
del LLM (anti-suplantación). `book_appointment` falla con `no_person` si el hilo aún no resolvió
su contacto (el LLM debe llamar antes a `resolve_or_create_contact`).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthContext
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.modules.admin.repositories.user import user_repository
from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.crm.services import person as crm_person
from app.modules.scheduling.enums import AppointmentSource
from app.modules.scheduling.repositories.appointment import appointment_repository
from app.modules.scheduling.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCreate,
)
from app.modules.scheduling.services import appointment as appointment_service
from app.modules.scheduling.services import availability as availability_service
from app.modules.scheduling.services import transition as transition_service

SYSTEM_USER_ID = crm_person.SYSTEM_USER_ID

# Cap de slots devueltos al LLM (un rango ancho × grano fino genera cientos; el prompt no
# debe explotar). Si se trunca, se avisa con `truncated` para que el bot acote el rango.
MAX_SLOTS_RETURNED = 30

DomainException = (BadRequestException, ConflictException, NotFoundException)


def _domain_error(
    exc: BadRequestException | ConflictException | NotFoundException,
) -> dict[str, Any]:
    """Traduce una excepción de dominio al result que ve el LLM (code estable o detalle)."""
    return {"ok": False, "error": exc.code or exc.detail}


@register_tool("check_availability")
async def check_availability(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Lista horarios LIBRES de un doctor para un producto en un rango de fechas (cómputo
    on-the-fly, ADR-006). El bot ofrece estos slots y luego usa book_appointment con uno."""
    try:
        from_date = date_type.fromisoformat(str(args["from_date"]))
        to_date = date_type.fromisoformat(str(args["to_date"]))
    except (KeyError, ValueError):
        return {"ok": False, "error": "invalid_date_range"}
    try:
        result = await availability_service.compute_available_slots(
            db,
            doctor_id=str(args["doctor_id"]),
            product_id=str(args["product_id"]),
            branch_id=args.get("branch_id"),
            office_id=args.get("office_id"),
            from_date=from_date,
            to_date=to_date,
        )
    except KeyError:
        return {"ok": False, "error": "missing_required_argument"}
    except DomainException as exc:
        return _domain_error(exc)
    slots = result.slots[:MAX_SLOTS_RETURNED]
    return {
        "ok": True,
        "slots": [
            {
                "starts_at": s.starts_at.isoformat(),
                "ends_at": s.ends_at.isoformat(),
                "office_id": s.office_id,
                "office_name": s.office_name,
                "doctor_name": s.doctor_name,
            }
            for s in slots
        ],
        "duration_min": result.duration_min,
        "truncated": len(result.slots) > MAX_SLOTS_RETURNED,
    }


@register_tool("book_appointment")
async def book_appointment(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Reserva una cita para el contacto del hilo (ctx.person_id) en el slot elegido.
    source='bot', created_by=SYSTEM. Valida los invariantes 1-8 (SLOT_TAKEN, DOCTOR_INACTIVE,
    OFFICE_CLOSED, …) en el service. El office_id y scheduled_for salen de un slot de
    check_availability."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    try:
        scheduled_for = datetime.fromisoformat(str(args["scheduled_for"]))
    except (KeyError, ValueError):
        return {"ok": False, "error": "invalid_scheduled_for"}
    try:
        payload = AppointmentCreate(
            person_id=ctx.person_id,
            doctor_id=str(args["doctor_id"]),
            office_id=str(args["office_id"]),
            product_id=str(args["product_id"]),
            scheduled_for=scheduled_for,
            source=AppointmentSource.bot,
            notes=args.get("notes"),
            # F4 (marketing): si el LLM pasó una promo elegible (de list_eligible_promotions),
            # create_appointment la aplica en la MISMA sesión. Una promo inválida lanza una
            # excepción de dominio de marketing (BadRequest/Conflict/NotFound) → la captura el
            # `except DomainException` de abajo y devuelve {ok:false, error:code}.
            apply_promotion_id=args.get("apply_promotion_id"),
        )
    except KeyError:
        return {"ok": False, "error": "missing_required_argument"}
    try:
        # F4: savepoint propio alrededor de create_appointment para que el book sea ATÓMICO en el
        # path del bot. Si `apply` (marketing) falla DESPUÉS de flushear la cita+history, el
        # begin_nested revierte ese trabajo parcial antes de que el except devuelva el code. Sin
        # esto, como el tool CAPTURA la excepción y retorna normal, el savepoint que el engine
        # (embedded.py) abre por tool se RELEASEaría → commitearía una cita huérfana SIN promo.
        # (El path HTTP ya es atómico por el rollback de get_db; el bot lo necesita aquí.)
        async with db.begin_nested():
            result = await appointment_service.create_appointment(
                db, payload, actor_id=SYSTEM_USER_ID
            )
    except DomainException as exc:
        return _domain_error(exc)
    appt = result.data
    return {
        "ok": True,
        "appointment_id": appt.id,
        "status": appt.status.code,
        "scheduled_for": appt.scheduled_for.isoformat(),
        "duration_min": appt.duration_min,
        "doctor_name": appt.doctor_name,
        "office_name": appt.office_name,
    }


@register_tool("cancel_appointment")
async def cancel_appointment(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Cancela una cita (→ CANCELLED) del contacto del hilo. Respeta min_hours_to_cancel: el
    bot NO tiene APPOINTMENTS_CANCEL_OVERRIDE → si falta poco para la cita devuelve
    CANCEL_TOO_LATE y el bot le pide al usuario que llame. Corre como SYSTEM (AuthContext con
    permisos vacíos)."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    try:
        appointment_id = str(args["appointment_id"])
    except KeyError:
        return {"ok": False, "error": "missing_required_argument"}
    # GUARD anti-IDOR: el bot SOLO cancela citas del contacto del hilo (ctx.person_id). Un id
    # de otra persona (LLM confundido/malicioso) → appointment_not_found (mismo error que una
    # cita inexistente: no se filtra la existencia de citas ajenas). El cancel del service
    # valida existencia + matriz, pero NO la pertenencia — esa es responsabilidad del facade.
    owned = await appointment_repository.get_by_id(db, appointment_id)
    if owned is None or owned.person_id != ctx.person_id:
        return {"ok": False, "error": "appointment_not_found"}
    # El cancel necesita el AuthContext completo (lee actor.id para cancelled_by y
    # actor.permissions para el override). Cargamos el SYSTEM user (seeded, no autenticable)
    # y lo envolvemos con permisos vacíos → respeta CANCEL_TOO_LATE.
    system_user = await user_repository.get_by_id(db, SYSTEM_USER_ID)
    if system_user is None:
        return {"ok": False, "error": "system_user_missing"}
    actor = AuthContext(user=system_user, permissions=frozenset(), roles=frozenset())
    try:
        result = await transition_service.cancel(
            db,
            appointment_id,
            AppointmentCancelRequest(cancellation_reason=args.get("cancellation_reason")),
            actor=actor,
        )
    except DomainException as exc:
        return _domain_error(exc)
    appt = result.data
    return {"ok": True, "appointment_id": appt.id, "status": appt.status.code}
