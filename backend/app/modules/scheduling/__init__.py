"""
Módulo `scheduling` (#7) — citas (`Appointment`) + cálculo on-the-fly de disponibilidad.

Persiste la cita como única unidad del calendario (ADR-006: NO hay tabla de slots); los slots
libres se calculan al vuelo (`compute_available_slots`) combinando insumos de otros módulos:
`staff.DoctorAvailability` (bloques concretos, ADR-007), `clinic.OfficeOperatingHours`/
`OfficeClosure`/`office_vertical`/`Branch.timezone`, `catalog.Product.duration_min`/
`min_hours_to_cancel`, y las citas activas del doctor. Cierra el loop de negocio
**lead → conversación/bot → cita → cliente**: al atender una cita se dispara
`crm.promote_to_customer` en la misma transacción. Lo consume `bots` vía 3 tools
(`check_availability`/`book_appointment`/`cancel_appointment`, fase final).

Transiciones de estado = matriz configurable (espeja crm, ADR-008). Diseño completo:
`docs/modules/scheduling/{README,backend,ui,frontend}.md` + ADR-006/007/008.

⚠ F0 (Prep): este paquete es un SKELETON INERTE — los `__init__.py` solo documentan la
estructura. **NO está registrado** en `app/modules/__init__.py` ni en `app/main.py` (lo cablea
F1, como hicieron crm/conversations/bots). Sin modelos/migración todavía → no aporta tablas ni
rutas. Migración inicial `0020_scheduling_status` (down_revision = `0019_bots_engine_state`).
"""
