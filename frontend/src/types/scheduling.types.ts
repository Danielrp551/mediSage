/**
 * Espejo TS de los Pydantic schemas del módulo `scheduling` (#7) — ver
 * `docs/modules/scheduling/{README,backend,ui,frontend}.md`, + ADR-006
 * (disponibilidad on-the-fly, sin tabla de slots), ADR-007 (bloques concretos de
 * disponibilidad del doctor) y ADR-008 (matriz de transiciones configurable,
 * reusada de crm). Importable desde server actions y client components. Reusa
 * `UserAuditInfo` de `audit.types` — NO se redefine.
 *
 * AUTORIDAD DE SHAPE: el contrato de runtime es `backend.md` (los Pydantic que
 * serializan el JSON); `frontend.md` es el molde de naming/precisión. Donde ambos
 * difieren gana `backend.md` (el JSON real). Reconciliaciones aplicadas:
 *   - `AppointmentItem.status` e history usan `AppointmentStatusOption` (backend.md),
 *     no un "Summary" (frontend.md driftó).
 *   - `AppointmentItem` NO trae confirmed_at/attended_at/cancelled_at ni notes/
 *     cancellation_reason/cancelled_by → son Detail-only (backend.md AppointmentDetail).
 *   - `AppointmentCreatePayload` NO lleva branch_id (el backend lo deriva de office);
 *     `Cancel` deja `cancellation_reason` opcional; `/me/appointments/list` devuelve
 *     el `AppointmentItem` completo (alias `MyAppointmentItem`).
 *   - `CalendarResponse` (no "AppointmentCalendarResponse"); la TZ del branch NO es un
 *     campo del schema (es cómputo de render; la grilla la resuelve client-side).
 *
 * Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún. Las pantallas
 * llegan por fase: Estados de cita + matriz (F1), Citas + wizard + disponibilidad
 * (F2), detalle + lifecycle + timeline (F3), grilla de calendario + Mi agenda (F4).
 * La facade del bot (from-bot/cancel-from-bot) es backend-only → sin tipos en el front.
 *
 * Notas de contrato que el código no expresa solo:
 *   - `AppointmentStatus.code` es MAYÚSCULAS sin pattern slug restrictivo (espeja
 *     crm.LeadStatus: SCHEDULED/CONFIRMED/…); inmutable post-create.
 *   - `scheduled_for`/`starts_at`/`ends_at`/`*_at`/`changed_at` son `timestamptz` ISO 8601
 *     con offset; `from_date`/`to_date` son fechas "YYYY-MM-DD" (rango de días).
 *   - `duration_min` lo COPIA el backend de `product.duration_min` (fallback
 *     `doctor.slot_duration_min`); el front NO lo manda en el create.
 *   - Denormalizados (`*_name`, `status`) los pobla el backend (batch maps) y SIEMPRE
 *     están presentes (toda cita tiene person/doctor/office/branch/product/status) →
 *     NO nullables; NO están en ALLOWED_FIELDS → no son server-sortable (lección cd10c78).
 *   - Trazas (history/changelog) SIN SoftDelete (audit honesto) y sin audit `updated_*`.
 */

import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de scheduling/enums.py; valores EXACTOS) ───

// Origen de la cita (código en appointment.source). Python: AppointmentSource(StrEnum), IMPORT="import".
export type AppointmentSource = "bot" | "advisor" | "admin" | "import" | "api";
export const APPOINTMENT_SOURCES: readonly AppointmentSource[] = [
  "bot",
  "advisor",
  "admin",
  "import",
  "api",
] as const;

// Razón de no-disponibilidad devuelta por POST /availability/check-slot (code en inglés;
// el front lo traduce con CHECK_SLOT_REASON_LABELS). Son los 9 codes de invariante de la spec.
export type CheckSlotReason =
  | "NO_AVAILABILITY_BLOCK"
  | "OFFICE_CLOSED"
  | "SLOT_TAKEN"
  | "OFFICE_SLOT_TAKEN"
  | "DOCTOR_INACTIVE"
  | "DOCTOR_NOT_APT_FOR_VERTICAL"
  | "OFFICE_NOT_APT_FOR_VERTICAL"
  | "DOCTOR_NOT_IN_BRANCH"
  | "OFFICE_NOT_IN_BRANCH";

// ── AppointmentStatus (catálogo configurable, espeja crm.LeadStatus sin is_won) ─

export interface AppointmentStatusItem {
  id: string;
  code: string; // MAYÚSCULAS, ej. "SCHEDULED" (inmutable)
  name: string;
  description: string | null;
  color: string | null; // hex para badges
  is_initial: boolean; // EXACTAMENTE uno true por catálogo (SCHEDULED)
  is_final: boolean; // terminal (ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED)
  is_active_attention: boolean; // 0..N "en atención ahora" (IN_PROGRESS)
  display_order: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Para dropdowns, badges, el editor de matriz, el StatusControl y el timeline (lista
// cruda en /active). Es el shape que el backend denormaliza como badge en Appointment.
export interface AppointmentStatusOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_initial: boolean;
  is_final: boolean;
  is_active_attention: boolean;
}

export interface AppointmentStatusCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_active_attention?: boolean;
  display_order?: number;
}

export interface AppointmentStatusUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_active_attention?: boolean;
  display_order?: number;
  active?: boolean;
}

// ── AppointmentStatusTransition (matriz, ADR-008) ───────────
// Fila cruda de la matriz; el front normalmente consume la forma resuelta
// TransitionTargets. SIN SoftDelete (deshabilitar arista = active=false / DELETE).
export interface AppointmentStatusTransitionItem {
  id: string;
  from_status_id: string;
  to_status_id: string;
  active: boolean;
  created_on: string;
  updated_on: string;
}

// Respuesta de GET /appointment-statuses/{id}/transitions: los estados a los que el
// estado {id} PUEDE ir (aristas de salida ya resueltas a Options).
export interface TransitionTargets {
  from_id: string;
  to: AppointmentStatusOption[];
}

// Body de PUT /appointment-statuses/{id}/transitions — REEMPLAZA las aristas de salida.
export interface TransitionTargetsReplacePayload {
  to_ids: string[];
}

// ── Disponibilidad on-the-fly (ADR-006/007; NO persiste) ────

export interface AvailabilityRequest {
  doctor_id: string;
  product_id: string;
  branch_id?: string | null; // opcional: acota a una sede
  office_id?: string | null; // opcional: acota a un consultorio
  from_date: string; // "YYYY-MM-DD" (inclusive)
  to_date: string; // "YYYY-MM-DD" (inclusive)
}

// Un slot libre computado. starts_at/ends_at son timestamptz UTC; el render los formatea
// client-only en la TZ del navegador/branch (lección TZ).
export interface AvailabilitySlot {
  starts_at: string; // ISO 8601 UTC
  ends_at: string; // ISO 8601 UTC (= starts_at + duration_min)
  doctor_id: string;
  doctor_name: string; // denormalizado
  office_id: string;
  office_name: string;
  branch_id: string;
  branch_name: string;
}

export interface AvailabilityResponse {
  slots: AvailabilitySlot[];
  duration_min: number; // duración del producto (fallback doctor.slot_duration_min)
  doctor_slot_duration_min: number; // grano del doctor (para alinear la grilla)
}

// Body de POST /availability/check-slot (revalida UN slot puntual antes de book).
export interface CheckSlotRequest {
  doctor_id: string;
  office_id: string;
  product_id: string;
  scheduled_for: string; // ISO 8601 UTC del inicio
}

export interface CheckSlotResponse {
  available: boolean;
  reason?: CheckSlotReason | null; // presente sólo si available=false
}

// ── Appointment (unidad persistida del calendario) ──────────

// Fila de listado. El backend DENORMALIZA (batch maps, sin N+1) person/doctor/office/
// branch/product/status. NINGUNO de los *_name está en ALLOWED_FIELDS → NO son
// server-sortable/filterable (lección cd10c78); el filtro va sobre columnas REALES
// (status_id/doctor_id/office_id/branch_id/product_id/scheduled_for). defaultSort = scheduled_for.
export interface AppointmentItem {
  id: string;
  person_id: string;
  person_name: string; // denorm de crm.Person (full_name)
  doctor_id: string;
  doctor_name: string; // denorm de staff.Doctor.user.full_name
  office_id: string;
  office_name: string; // denorm de clinic.Office.name
  branch_id: string;
  branch_name: string; // denorm de clinic.Branch.name (DENORM de office.branch_id)
  product_id: string;
  product_name: string; // denorm de catalog.Product.name
  scheduled_for: string; // timestamptz UTC (inicio)
  duration_min: number; // copiado de product al agendar
  status: AppointmentStatusOption; // badge (id/code/name/color/flags)
  source: AppointmentSource;
  previous_appointment_id: string | null; // cadena de reagendamiento
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + notas/cancelación/confirmación/atención + el timeline (history +
// change_log embebidos en un solo GET). La cita NO se soft-deletea al cerrar (la fila
// vive como histórico; diverge de crm).
export interface AppointmentDetail extends AppointmentItem {
  notes: string | null;
  cancellation_reason: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  confirmed_at: string | null;
  attended_at: string | null;
  status_history: AppointmentStatusHistoryItem[];
  change_log: AppointmentChangeLogItem[];
}

// Referencia compacta (no hay /active de citas; la usan la cadena de reagendamiento y
// respuestas internas).
export interface AppointmentOption {
  id: string;
  scheduled_for: string;
  doctor_name: string;
  person_name: string;
}

// Body de POST /appointments (create/book) — lo arma el wizard al confirmar. `branch_id`
// lo DERIVA el backend de office; `duration_min` lo COPIA de product; `status_id` nace en
// el is_initial; `source` lo fija el actor (advisor/admin). El service valida los 9
// invariantes + SLOT_TAKEN (SELECT FOR UPDATE).
export interface AppointmentCreatePayload {
  person_id: string;
  doctor_id: string;
  office_id: string;
  product_id: string;
  scheduled_for: string; // ISO 8601 UTC del slot elegido
  source?: AppointmentSource; // default advisor (lo setea la action según el rol)
  notes?: string | null;
}

// Body de PUT /appointments/{id} — SOLO columnas no-estado (→ change_log). scheduled_for
// NO se edita aquí (usa /reschedule); status_id NO se edita aquí (usa /transition o
// shortcuts). branch_id se re-deriva si cambia office_id (no se manda).
export interface AppointmentUpdatePayload {
  doctor_id?: string;
  office_id?: string;
  product_id?: string;
  notes?: string | null;
  reason?: string | null; // se escribe en change_log.reason
}

// ── Ciclo de vida (valida la matriz configurable) ───────────

// POST /appointments/{id}/transition — transición genérica explícita. Los shortcuts
// (/confirm /check-in /start /attend /no-show) resuelven su to_status por code en el
// backend; el front los invoca sin body (o con un reason opcional vía este shape).
export interface AppointmentTransitionPayload {
  to_status_id: string;
  reason?: string | null;
}

// POST /appointments/{id}/cancel. El override de min_hours_to_cancel es por PERMISO
// (APPOINTMENTS_CANCEL_OVERRIDE), no un flag del body.
export interface AppointmentCancelPayload {
  cancellation_reason?: string | null;
}

// POST /appointments/{id}/reschedule — marca la vieja RESCHEDULED y crea la nueva con
// previous_appointment_id en la misma transacción (no sujeto a min_hours_to_cancel).
// doctor_id/office_id opcionales = se reusan los de la cita vieja.
export interface AppointmentReschedulePayload {
  scheduled_for: string; // nuevo inicio (ISO 8601 UTC)
  doctor_id?: string;
  office_id?: string;
  reason?: string | null;
}

// ── Trazas (timeline de cambios; SIN SoftDelete, audit honesto) ─

// from_status null en el primer cambio (NULL→initial). Emite Options (backend.md).
export interface AppointmentStatusHistoryItem {
  id: string;
  appointment_id: string;
  from_status: AppointmentStatusOption | null;
  to_status: AppointmentStatusOption;
  changed_at: string; // timestamptz ISO 8601
  changed_by: string | null; // null/SYSTEM si automático (bot/sistema)
  changed_by_user: UserAuditInfo | null; // resuelto batch; null si SYSTEM/hard-deleted
  reason: string | null;
}

// Cambios in-place de columnas NO-estado (doctor_id/office_id/notes/…).
export interface AppointmentChangeLogItem {
  id: string;
  appointment_id: string;
  field_name: string; // "doctor_id" | "office_id" | "notes" | …
  previous_value: string | null; // serializado (UUID/ISO8601/string)
  new_value: string | null;
  changed_at: string;
  changed_by: string | null;
  changed_by_user: UserAuditInfo | null;
  reason: string | null;
}

// ── Calendario (grilla, F4) ─────────────────────────────────
// GET /appointments/calendar (+ /me/calendar). `free_slots` solo se pobla cuando hay
// doctor_id + product_id en el request (el cómputo es por doctor+producto). La TZ del
// branch para pintar la grilla la resuelve el render client-side (no es un campo del schema).
export interface CalendarResponse {
  appointments: AppointmentItem[];
  free_slots: AvailabilitySlot[];
  from_date: string; // "YYYY-MM-DD" (eco del request)
  to_date: string;
}

// ── Self-service del doctor ─────────────────────────────────
// GET/POST /me/appointments/list devuelve el AppointmentItem completo (backend.md);
// alias para nombrar el sub-recurso del doctor sin duplicar el shape.
export type MyAppointmentItem = AppointmentItem;
