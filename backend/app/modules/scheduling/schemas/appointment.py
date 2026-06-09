"""
Schemas Pydantic v2 de Appointment. Espejo de `frontend/src/types/scheduling.types.ts`.

F2 (este commit): AppointmentCreate (book) + AppointmentItem (tabla) + AppointmentDetail
(detalle con trazas) + AppointmentOption (referencia compacta). Los requests de
lifecycle (Update/Transition/Cancel/Reschedule) llegan en F3 con sus endpoints.

`branch_id`/`duration_min` NO se aceptan del cliente: el backend los DERIVA (branch de
office; duration de product, fallback doctor.slot_duration_min). El estado nace en el
is_initial. Los denormalizados (*_name, status) los pobla el service vía batch maps
(sin N+1) y NO van en ALLOWED_FIELDS (lección cd10c78).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.scheduling.enums import AppointmentSource
from app.modules.scheduling.schemas.appointment_status import AppointmentStatusOption
from app.modules.scheduling.schemas.audit import (
    AppointmentChangeLogItem,
    AppointmentStatusHistoryItem,
)


class AppointmentCreate(BaseModel):
    """Body de POST /appointments (book). duration_min NO se acepta (se copia de
    product, fallback doctor.slot_duration_min). branch_id NO se acepta (se deriva de
    office.branch_id). El estado nace en el is_initial."""

    person_id: str = Field(min_length=1)
    doctor_id: str = Field(min_length=1)
    office_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    scheduled_for: datetime  # inicio, UTC
    source: AppointmentSource = AppointmentSource.advisor
    notes: str | None = None
    # F4 (marketing): si viene, se aplica una promo a la cita recién creada en la MISMA
    # sesión (atómico). NO es columna de Appointment — el vínculo vive en promotion_usage.
    # appointment_id. Si la promo es inválida, el rollback global revierte la cita.
    apply_promotion_id: str | None = None


class AppointmentUpdate(BaseModel):
    """Body de PUT /appointments/{id} (F3) — SOLO columnas no-estado y no-tiempo (cada
    cambio → AppointmentChangeLog). status_id se cambia por /transition; scheduled_for
    por /reschedule. branch_id/duration_min se re-derivan si cambia office/product."""

    doctor_id: str | None = None
    office_id: str | None = None
    product_id: str | None = None
    notes: str | None = None
    reason: str | None = Field(default=None, max_length=255)  # para el changelog


class AppointmentTransitionRequest(BaseModel):
    """Body de POST /appointments/{id}/transition (F3, genérico, valida la matriz)."""

    to_status_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class AppointmentCancelRequest(BaseModel):
    """Body de POST /appointments/{id}/cancel (F3)."""

    cancellation_reason: str | None = Field(default=None, max_length=255)


class AppointmentRescheduleRequest(BaseModel):
    """Body de POST /appointments/{id}/reschedule (F3). Crea una cita NUEVA (mismo
    person/product por defecto; doctor/office/scheduled_for nuevos) y marca la vieja
    RESCHEDULED. doctor_id/office_id opcionales = se reusan los de la cita vieja."""

    scheduled_for: datetime  # nuevo inicio, UTC
    doctor_id: str | None = None
    office_id: str | None = None
    reason: str | None = Field(default=None, max_length=255)


class AppointmentItem(BaseModel):
    """Fila de la tabla de citas. Denormaliza person/doctor/office/branch/product + el
    badge de estado para que la lista no joinee. NINGUNO de los denormalizados va en
    ALLOWED_FIELDS; el filtro por doctor/estado/sede/producto/fecha = columnas reales."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    person_name: str  # denorm de crm.Person
    doctor_id: str
    doctor_name: str  # denorm de staff.Doctor.user.full_name
    office_id: str
    office_name: str  # denorm de clinic.Office.name
    branch_id: str
    branch_name: str  # denorm de clinic.Branch.name
    product_id: str
    product_name: str  # denorm de catalog.Product.name
    scheduled_for: datetime
    duration_min: int
    status: AppointmentStatusOption  # badge (id/code/name/color/flags)
    source: AppointmentSource
    previous_appointment_id: str | None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class AppointmentDetail(AppointmentItem):
    """Detalle completo: agrega notas/cancelación/confirmación/atención + el timeline
    (status_history + change_log). El service arma las listas explícitamente."""

    notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    cancelled_by: str | None
    confirmed_at: datetime | None
    attended_at: datetime | None
    status_history: list[AppointmentStatusHistoryItem]
    change_log: list[AppointmentChangeLogItem]


class AppointmentOption(BaseModel):
    """Referencia compacta — no hay /active de citas, pero el shape lo usan la cadena de
    reagendamiento y respuestas internas."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    scheduled_for: datetime
    doctor_name: str
    person_name: str
