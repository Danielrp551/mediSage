"""
Modelos SQLAlchemy del módulo `scheduling` (F1+). 5 entidades (sin M:N):
- `AppointmentStatus` (F1) — catálogo configurable de estados de cita (espeja crm.LeadStatus;
  `code` MAYÚSCULAS sin pattern slug; flags is_initial/is_final/is_active_attention). PK·A·SD·T.
- `AppointmentStatusTransition` (F1) — matriz `from→to` (UNIQUE; espeja crm, ADR-008). PK·A·T (sin SD).
- `Appointment` (F2) — cita: person/doctor/office/branch[denorm]/product + scheduled_for + duration_min
  + status_id + source(bot|advisor|admin|import|api) + previous_appointment_id(self-FK). PK·A·SD·T.
  NO se soft-deletea al cerrar (la fila vive como histórico; DIVERGE de crm).
- `AppointmentStatusHistory` (F2) — timeline append-only de transiciones de estado. PK·A·T (sin SD).
- `AppointmentChangeLog` (F2) — traza de cambios in-place de columnas no-estado. PK·A·T (sin SD).

Las trazas y la matriz NO llevan SoftDelete (auditoría honesta + config). Las FKs forward a
`person`/`doctor`/`office`/`branch`/`product`/`user`/`appointment_status` + la self-FK las crea
la migración con `create_foreign_key` (el smoke sqlite no las ejercita; las valida el QA E2E en
Postgres). Sin relationship al padre en las trazas (acceso por `appointment_id` + batch maps).
INERTE en F0.
"""
