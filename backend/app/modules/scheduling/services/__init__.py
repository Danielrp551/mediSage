"""
Services del módulo `scheduling` (F1+), módulos de funciones (no clases). Incluye:
- `appointment_status` (F1) — CRUD catálogo + matriz (espeja crm; `MULTIPLE_INITIAL_STATUS`).
- `availability` (F2) — `compute_available_slots` (corazón, ADR-006/007; NO persiste) + check-slot.
- `appointment` (F2/F3) — create/book (9 invariantes + `SLOT_TAKEN` con SELECT FOR UPDATE),
  reschedule (revalida sobre la nueva cita, marca la vieja RESCHEDULED, misma tx), cancel
  (`min_hours_to_cancel` salvo `APPOINTMENTS_CANCEL_OVERRIDE`), transiciones (consultan la matriz)
  + shortcuts (confirm/check-in/start/attend/no-show) + history/changelog. El `attend→ATTENDED`
  dispara `crm.promote_to_customer` ATÓMICO (misma tx) + emite `LeadActivity(APPOINTMENT_ATTENDED)`.
- `bot_facade` (F5) — `book_from_bot`/`cancel_from_bot` como SYSTEM (source='bot', respetan TODOS
  los invariantes; el bot NO hace override). Registra 3 tools en `bots.TOOL_REGISTRY`.

Doctor `active=false` excluido de nuevas reservas (`DOCTOR_INACTIVE`; gate de scheduling, diverge
de staff). INERTE en F0.
"""
