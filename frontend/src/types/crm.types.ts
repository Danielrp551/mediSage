/**
 * Espejo TS de los Pydantic schemas del módulo `crm` (ver
 * `docs/modules/crm/backend.md` y `docs/modules/crm/frontend.md`). Importable
 * desde server actions y client components. Reusa `UserAuditInfo` de
 * `audit.types` — no se redefine. SIN dependencias a otros módulos de dominio:
 * las 3 columnas forward (`source_campaign_id`, `related_appointment_id`,
 * `related_conversation_id`) son strings opacos de solo lectura (sus módulos
 * dueños — marketing/scheduling/conversations — aún no existen).
 *
 * Declarado en F0 (Prep). Las pantallas que los consumen llegan por fases:
 * Person + Identifiers (F1), catálogos LeadStatus/CustomerStatus + matriz (F2),
 * lifecycle lead + assignment + Mis leads (F3), lifecycle customer (F4),
 * timeline rico de actividad (F5).
 */

import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de crm/enums.py; valores EXACTOS) ─────────

// Slugs estables que cruzan con conversations.ChannelAccount.channel_type a futuro.
export type ChannelType =
  | "whatsapp"
  | "telegram"
  | "web"
  | "phone"
  | "email"
  | "instagram"
  | "facebook"
  | "other";

export const CHANNEL_TYPES: readonly ChannelType[] = [
  "whatsapp",
  "telegram",
  "web",
  "phone",
  "email",
  "instagram",
  "facebook",
  "other",
] as const;

// Enum COMPLETO desde el inicio (contrato estable). En el MVP crm sólo se EMITEN
// NOTE/CALL_ATTEMPT/FOLLOW_UP_*/STATUS_CHANGE/REASSIGNED/CAMPAIGN_ATTRIBUTION;
// los MESSAGE_*/CONVERSATION_*/APPOINTMENT_* están presentes pero los emite
// conversations/scheduling más adelante (el front debe saber renderizarlos
// cuando aparezcan en el timeline). Ver README §1.2.
export type ActivityType =
  | "CALL_ATTEMPT"
  | "NOTE"
  | "STATUS_CHANGE"
  | "FOLLOW_UP_SCHEDULED"
  | "FOLLOW_UP_COMPLETED"
  | "MESSAGE_SENT"
  | "CONVERSATION_TAKEN"
  | "CONVERSATION_RELEASED"
  | "APPOINTMENT_BOOKED"
  | "APPOINTMENT_CANCELLED"
  | "REASSIGNED"
  | "CAMPAIGN_ATTRIBUTION";

// Sólo aplica a CALL_ATTEMPT (resultado de la llamada).
export type ActivityOutcome =
  | "successful"
  | "no_answer"
  | "busy"
  | "wrong_number"
  | "not_interested"
  | "interested";

// ── Person ──────────────────────────────────────────────

// Fila de listado. El backend DENORMALIZA (batch maps, sin N+1) el contacto
// principal, los estados lead/customer (code/name/color), el asesor y la última
// actividad. NINGUNO de estos denormalizados está en ALLOWED_FIELDS → NO son
// server-sortable/filterable (lección cd10c78). Filtro por estado/asesor en el
// listado = deep-link traducido a EXISTS/JOIN server-side (campos "virtuales"),
// NO order-by sobre el denormalizado.
export interface PersonItem {
  id: string;
  first_name: string;
  last_name: string;
  second_last_name: string | null;
  full_name: string; // denormalizado — first + last (+ second) compuesto server-side
  document_type: string | null;
  document_number: string | null;
  // Contacto principal: el identifier is_primary preferido (whatsapp/phone/email)
  // resuelto server-side. null si la persona no tiene identifiers.
  primary_identifier: PersonPrimaryIdentifier | null;
  // Estado lead ACTIVO (null si no tiene PersonLeadStatus vivo). Subset del catálogo.
  lead_status: LeadStatusSummary | null;
  // Estado cliente ACTIVO (null si no es cliente). Subset del catálogo.
  customer_status: CustomerStatusSummary | null;
  // Asesor dueño del lead activo (null si no tiene LeadAssignment).
  assigned_advisor: UserAuditInfo | null;
  // Denormalizado de PersonLeadStatus.last_activity_at (timestamptz, ISO 8601 o null).
  last_activity_at: string | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Subset del identifier principal embebido en PersonItem/PersonDetail.
export interface PersonPrimaryIdentifier {
  channel_type: ChannelType;
  identifier: string;
  verified: boolean;
}

// Subset de LeadStatus para badges en listados/detalle (evita el join completo).
export interface LeadStatusSummary {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
  is_won: boolean;
}

// Subset de CustomerStatus (sin is_won).
export interface CustomerStatusSummary {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
}

// Detalle de la persona: identidad completa + identifiers expandidos. Los estados
// lead/customer y la asignación se cargan en sus tabs (sub-recursos), NO viajan
// inflando el detalle (mismo criterio que DoctorDetail no trae la disponibilidad).
export interface PersonDetail {
  id: string;
  first_name: string;
  last_name: string;
  second_last_name: string | null;
  full_name: string;
  document_type: string | null;
  document_number: string | null;
  birth_date: string | null; // "YYYY-MM-DD" (date sin TZ)
  gender: string | null; // texto libre, sin enum
  address: string | null;
  notes: string | null;
  identifiers: PersonContactIdentifierItem[]; // multicanal, soft-deleted filtradas server-side
  // Resúmenes para el header (los detalles completos los traen los tabs).
  lead_status: LeadStatusSummary | null;
  customer_status: CustomerStatusSummary | null;
  assigned_advisor: UserAuditInfo | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Para dropdowns (selección de una persona en scheduling/conversations a futuro,
// y el endpoint /persons/search del bot). Lista CRUDA (sin envelope).
export interface PersonOption {
  id: string;
  full_name: string;
  document_number: string | null;
  primary_identifier: PersonPrimaryIdentifier | null;
}

// Identificadores iniciales opcionales que viajan ANIDADOS en el create de Person.
export interface PersonIdentifierCreatePayload {
  channel_type: ChannelType;
  identifier: string;
  is_primary?: boolean; // default false
  verified?: boolean; // default false
}

export interface PersonCreatePayload {
  first_name: string;
  last_name: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  birth_date?: string | null; // "YYYY-MM-DD"
  gender?: string | null;
  address?: string | null;
  notes?: string | null;
  // Identificadores iniciales (opcional). El service valida dedup en el mismo body
  // y contra BD (UNIQUE(channel_type, identifier) parcial). NO crea lead automático.
  identifiers?: PersonIdentifierCreatePayload[];
}

export interface PersonUpdatePayload {
  first_name?: string;
  last_name?: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  birth_date?: string | null;
  gender?: string | null;
  address?: string | null;
  notes?: string | null;
  active?: boolean;
}

// ── PersonContactIdentifier ─────────────────────────────

export interface PersonContactIdentifierItem {
  id: string;
  person_id: string;
  channel_type: ChannelType;
  identifier: string; // valor (phone E.164, email, chat_id…)
  is_primary: boolean;
  verified: boolean;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface ContactIdentifierCreatePayload {
  channel_type: ChannelType;
  identifier: string;
  is_primary?: boolean;
  verified?: boolean;
}

export interface ContactIdentifierUpdatePayload {
  channel_type?: ChannelType;
  identifier?: string;
  is_primary?: boolean;
  verified?: boolean;
}

// ── LeadStatus (catálogo configurable) ──────────────────

export interface LeadStatusItem {
  id: string;
  code: string; // slug mayúsculas, ej. "NUEVO"
  name: string;
  description: string | null;
  color: string | null; // hex para badges
  is_initial: boolean; // exactamente uno true por catálogo
  is_final: boolean; // terminal
  is_won: boolean; // terminal positivo; sólo válido si is_final=true
  display_order: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Para dropdowns y el TransitionControl (lista cruda en /active).
export interface LeadStatusOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_initial: boolean;
  is_final: boolean;
  is_won: boolean;
}

export interface LeadStatusCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_won?: boolean;
  display_order?: number;
}

export interface LeadStatusUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_won?: boolean;
  display_order?: number;
  active?: boolean;
}

// ── CustomerStatus (catálogo) — igual SIN is_won ────────

export interface CustomerStatusItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  color: string | null;
  is_initial: boolean;
  is_final: boolean;
  display_order: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface CustomerStatusOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_initial: boolean;
  is_final: boolean;
}

export interface CustomerStatusCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  display_order?: number;
}

export interface CustomerStatusUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  display_order?: number;
  active?: boolean;
}

// ── Matriz de transiciones (ADR-008) ────────────────────
// Respuesta de GET /lead-statuses/{id}/transitions: los estados a los que el
// estado {id} PUEDE ir (las aristas de salida ya resueltas a Options).
export interface TransitionTargets {
  from_id: string;
  to: LeadStatusOption[]; // (CustomerStatusOption[] para el catálogo customer)
}

// La variante customer (mismo shape, Options de customer).
export interface CustomerTransitionTargets {
  from_id: string;
  to: CustomerStatusOption[];
}

// Body de PUT /lead-statuses/{id}/transitions — REEMPLAZA las aristas de salida.
export interface TransitionTargetsReplacePayload {
  to_ids: string[];
}

// ── PersonLeadStatus (estado lead activo) ───────────────

export interface PersonLeadStatusDetail {
  id: string;
  person_id: string;
  lead_status: LeadStatusOption; // estado actual resuelto
  source_campaign_id: string | null; // forward FK (varchar opaco, solo lectura)
  entered_status_at: string; // timestamptz ISO 8601
  last_activity_at: string | null;
  created_on: string;
}

// Body de POST /persons/{id}/lead-status (crear lead; nace en is_initial).
export interface CreateLeadPayload {
  source_campaign_id?: string | null;
  reason?: string | null;
}

// ── PersonCustomerStatus (estado cliente activo) ────────

export interface PersonCustomerStatusDetail {
  id: string;
  person_id: string;
  customer_status: CustomerStatusOption;
  became_customer_at: string; // primera vez (timestamptz ISO 8601)
  entered_status_at: string; // estado actual
  created_on: string;
}

// ── Transiciones de estado de un Person ─────────────────

export interface LeadTransitionPayload {
  to_lead_status_id: string;
  reason?: string | null;
}

export interface CustomerTransitionPayload {
  to_customer_status_id: string;
  reason?: string | null;
}

// Body opcional del promote-to-customer (estado inicial implícito = is_initial).
export interface PromoteToCustomerPayload {
  reason?: string | null;
}

// ── Historiales (timeline de cambios de estado) ─────────
// SIN soft-delete (audit trail honesto). from_*_status_id null en el primer cambio.

export interface LeadStatusHistoryItem {
  id: string;
  person_id: string;
  // El backend (schemas/lead_lifecycle.py) emite LeadStatusOption en el history,
  // igual que PersonLeadStatusDetail.lead_status (incluye is_initial). null al crear.
  from_lead_status: LeadStatusOption | null; // null al crear (NULL→initial)
  to_lead_status: LeadStatusOption;
  source_campaign_id: string | null;
  changed_at: string; // timestamptz ISO 8601
  changed_by: string | null; // FK lógica → user (null/SYSTEM si automático)
  changed_by_user: UserAuditInfo | null; // resuelto batch; null si SYSTEM/hard-deleted
  reason: string | null;
}

export interface CustomerStatusHistoryItem {
  id: string;
  person_id: string;
  // El backend (schemas/customer_lifecycle.py) emite CustomerStatusOption en el
  // history, igual que PersonCustomerStatusDetail.customer_status. null en la
  // promoción inicial (NULL→initial).
  from_customer_status: CustomerStatusOption | null;
  to_customer_status: CustomerStatusOption;
  changed_at: string;
  changed_by: string | null;
  changed_by_user: UserAuditInfo | null;
  reason: string | null;
}

// ── LeadAssignment (owner del lead) ─────────────────────

export interface LeadAssignmentDetail {
  id: string;
  person_id: string;
  advisor: UserAuditInfo; // asesor dueño resuelto
  assigned_at: string; // timestamptz ISO 8601
  assigned_by: string | null; // null/SYSTEM si round-robin automático
  assigned_by_user: UserAuditInfo | null;
  reason: string | null;
}

// Body de PUT /persons/{id}/assignment (manual / "asignarme").
export interface AssignmentPayload {
  advisor_user_id: string;
  reason?: string | null;
}

// Lista cruda de GET /advisors/active — asesores para el dropdown de asignación.
// Es crm-owned (no admin/users); el round-robin filtra user con role=ASESOR.
export interface AdvisorOption {
  id: string;
  full_name: string;
}

// Fila de /me/leads/list (leads del asesor logueado). Mismo perfil que PersonItem
// recortado a lo que el asesor necesita; trae el próximo seguimiento denormalizado.
export interface MyLeadItem {
  person_id: string;
  full_name: string;
  primary_identifier: PersonPrimaryIdentifier | null;
  lead_status: LeadStatusSummary | null;
  last_activity_at: string | null;
  next_follow_up_at: string | null; // próximo FOLLOW_UP_SCHEDULED pendiente (o null)
}

// ── LeadActivity (timeline polimórfico) ─────────────────
// SIN soft-delete: "borrar" = active=false (el feed normal filtra active=true).

export interface LeadActivityItem {
  id: string;
  person_id: string;
  advisor_user_id: string | null; // null/SYSTEM para actividades del sistema
  advisor: UserAuditInfo | null; // resuelto batch; null si SYSTEM/hard-deleted
  activity_type: ActivityType;
  content: string | null;
  scheduled_for: string | null; // timestamptz — FOLLOW_UP_SCHEDULED
  completed_at: string | null;
  outcome: ActivityOutcome | null; // sólo CALL_ATTEMPT
  payload: Record<string, unknown> | null; // datos específicos por tipo (JSONB)
  related_appointment_id: string | null; // forward FK (varchar opaco)
  related_conversation_id: string | null; // forward FK (varchar opaco)
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Crear una actividad (sólo los tipos editables por el asesor en el MVP). El
// activity_type discrimina qué campos son obligatorios (ver Zod superRefine).
export interface LeadActivityCreatePayload {
  activity_type: Extract<
    ActivityType,
    "NOTE" | "CALL_ATTEMPT" | "FOLLOW_UP_SCHEDULED" | "FOLLOW_UP_COMPLETED"
  >;
  content?: string | null;
  scheduled_for?: string | null; // obligatorio para FOLLOW_UP_SCHEDULED
  completed_at?: string | null;
  outcome?: ActivityOutcome | null; // sólo CALL_ATTEMPT
  payload?: Record<string, unknown> | null;
}

// Editar una actividad: SOLO content/outcome/completed_at/scheduled_for (el backend
// rechaza cambiar activity_type/person_id/advisor). Todos opcionales.
export interface LeadActivityUpdatePayload {
  content?: string | null;
  outcome?: ActivityOutcome | null;
  completed_at?: string | null;
  scheduled_for?: string | null;
}

// Body de POST /persons/{id}/activities/list — filtros del timeline (re-query
// del lado servidor; alternativa al filtrado client-side de los chips).
export interface ActivityListRequest {
  activity_type?: ActivityType[]; // vacío/ausente = todos
  date_from?: string; // ISO 8601 datetime, ej. "2026-05-01T00:00:00Z" (Pydantic acepta date-only → medianoche)
  date_to?: string;
}
