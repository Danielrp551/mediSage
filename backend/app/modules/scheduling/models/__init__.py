"""
Modelos SQLAlchemy del módulo `scheduling`. Importarlos acá los registra en
Base.metadata antes de que Alembic lea el esquema y antes de resolver los
relationship() por string.

F1 (este commit): catálogo + matriz.
- `AppointmentStatus` — catálogo configurable de estados de cita (espeja crm.LeadStatus;
  `code` MAYÚSCULAS sin pattern; flags is_initial/is_final/is_active_attention). PK·A·SD·T.
- `AppointmentStatusTransition` — matriz `from→to` (UNIQUE; espeja crm, ADR-008). PK·A·T (sin SD).

F2 sumará: `Appointment` (self-FK previous_appointment_id) + `AppointmentStatusHistory` +
`AppointmentChangeLog` (las dos trazas sin SoftDelete).
"""

from app.modules.scheduling.models.appointment_status import AppointmentStatus
from app.modules.scheduling.models.appointment_status_transition import (
    AppointmentStatusTransition,
)

__all__ = [
    "AppointmentStatus",
    "AppointmentStatusTransition",
]
