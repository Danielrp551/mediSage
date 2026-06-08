"""
Modelos SQLAlchemy del módulo `scheduling`. Importarlos acá los registra en
Base.metadata antes de que Alembic lea el esquema y antes de resolver los
relationship() por string.

F1: catálogo + matriz.
- `AppointmentStatus` — catálogo configurable de estados de cita (espeja crm.LeadStatus;
  `code` MAYÚSCULAS sin pattern; flags is_initial/is_final/is_active_attention). PK·A·SD·T.
- `AppointmentStatusTransition` — matriz `from→to` (UNIQUE; espeja crm, ADR-008). PK·A·T (sin SD).

F2 (este commit): la cita persistida + sus dos trazas.
- `Appointment` — unidad del calendario (self-FK previous_appointment_id; FKs reales a
  person/doctor/office/branch/product/user; SIN relationship ORM). PK·A·SD·T.
- `AppointmentStatusHistory` — timeline append-only de transiciones de estado. PK·A·T (sin SD).
- `AppointmentChangeLog` — traza de cambios in-place de columnas no-estado. PK·A·T (sin SD).

Orden: catálogo + matriz antes que appointment; appointment antes que sus trazas.
"""

from app.modules.scheduling.models.appointment import Appointment
from app.modules.scheduling.models.appointment_change_log import AppointmentChangeLog
from app.modules.scheduling.models.appointment_status import AppointmentStatus
from app.modules.scheduling.models.appointment_status_history import (
    AppointmentStatusHistory,
)
from app.modules.scheduling.models.appointment_status_transition import (
    AppointmentStatusTransition,
)

__all__ = [
    "AppointmentStatus",
    "AppointmentStatusTransition",
    "Appointment",
    "AppointmentStatusHistory",
    "AppointmentChangeLog",
]
