/**
 * Espejo TS de los Pydantic schemas del módulo `conversations` (ver
 * `docs/modules/conversations/backend.md` / `frontend.md` y el README como
 * fuente de verdad consolidada). Importable desde server actions y client
 * components. Reusa `UserAuditInfo` de `audit.types` y `ChannelType` de
 * `crm.types` — NO se redefinen (la spec dice explícitamente que `ChannelType`
 * es single source of truth en crm; el docstring de `crm/enums.py` confirma que
 * "the slug crosses with conversations.ChannelAccount.channel_type").
 *
 * Las dos columnas forward (`bot_configuration_id`, `default_campaign_id`) son
 * strings opacos de solo lectura — bots (#6) y marketing (#8) aún no existen
 * (ADR-009); hoy SIEMPRE null.
 *
 * Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume todavía. Las
 * pantallas llegan por fases: Canales (F1), inbox recibir+ver (F2), handoff +
 * outbound + mi bandeja (F3), adjuntos/media (F4 diferida).
 *
 * El SECRETO NUNCA viaja al front: ChannelAccount* exponen `secret_name` (solo
 * el nombre del secreto en GCP Secret Manager) + un flag `credentials_configured`
 * derivado server-side; el access_token/app_secret jamás salen del backend.
 */

import type { UserAuditInfo } from "./audit.types";
// ChannelType se REUSA de crm (single source of truth). NO redefinir.
import type { ChannelType } from "./crm.types";

// ── Enums (espejo de conversations/enums.py; valores EXACTOS) ─────────

// Estado del hilo. closed = cerrado (soft, vía status; el hilo NO se soft-deletea).
export type ConversationStatus = "open" | "closed";
export const CONVERSATION_STATUSES: readonly ConversationStatus[] = ["open", "closed"] as const;

// A quién está asignada la conversación. advisor ⟺ assignee_user_id NOT NULL.
export type AssigneeType = "bot" | "advisor" | "unassigned";
export const ASSIGNEE_TYPES: readonly AssigneeType[] = ["bot", "advisor", "unassigned"] as const;

// Dirección del mensaje (relativo a la clínica).
export type MessageDirection = "inbound" | "outbound";
export const MESSAGE_DIRECTIONS: readonly MessageDirection[] = ["inbound", "outbound"] as const;

// Quién originó el mensaje. advisor ⟺ sender_user_id NOT NULL.
export type SenderType = "contact" | "bot" | "advisor" | "system";
export const SENDER_TYPES: readonly SenderType[] = ["contact", "bot", "advisor", "system"] as const;

// Tipo de contenido. MVP solo emite/acepta "text" (composer). El resto está en el
// contrato para cuando F4 cablee media; el front sabe pintar un placeholder.
export type ContentType =
  | "text"
  | "image"
  | "audio"
  | "video"
  | "document"
  | "location"
  | "sticker"
  | "contact_card"
  | "system_notification";
export const CONTENT_TYPES: readonly ContentType[] = [
  "text",
  "image",
  "audio",
  "video",
  "document",
  "location",
  "sticker",
  "contact_card",
  "system_notification",
] as const;

// Tipo de adjunto (modelado; processing diferido a F4).
export type AttachmentType =
  | "image"
  | "audio"
  | "video"
  | "document"
  | "location"
  | "sticker"
  | "contact_card";
export const ATTACHMENT_TYPES: readonly AttachmentType[] = [
  "image",
  "audio",
  "video",
  "document",
  "location",
  "sticker",
  "contact_card",
] as const;

// Estados conocidos del provider en external_status (la columna es varchar libre,
// pero estos son los valores que el front sabe renderizar con ticks/íconos).
export type MessageExternalStatus = "sent" | "delivered" | "read" | "failed";
export const MESSAGE_EXTERNAL_STATUSES: readonly MessageExternalStatus[] = [
  "sent",
  "delivered",
  "read",
  "failed",
] as const;

// ── ChannelAccount ──────────────────────────────────────

// Fila de listado (tabla de Canales). El secreto NUNCA viaja: Item/Detail exponen
// `secret_name` (solo el nombre del secreto en GCP Secret Manager) y un flag
// `credentials_configured` derivado server-side — el token/app_secret jamás salen.
export interface ChannelAccountItem {
  id: string;
  channel_type: ChannelType;
  name: string; // nombre humano ("WhatsApp Estética")
  external_identifier: string; // número WA Business (ej. "51999111222")
  secret_name: string | null; // nombre del secreto en Secret Manager (NO el secreto)
  credentials_configured: boolean; // derivado: secret_name set || fallback env disponible
  phone_number_id: string | null; // id del número en WhatsApp Cloud API (para la URL de envío)
  // Forward FKs (bots #6 / marketing #8 — varchar opaco, solo lectura; ADR-009).
  bot_configuration_id: string | null; // hoy SIEMPRE null
  default_campaign_id: string | null; // hoy null
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + el webhook_verify_token (editable; NO es secreto duro — lo envía
// Meta y se compara). El secreto SIGUE sin exponerse (solo secret_name + flag).
export interface ChannelAccountDetail extends ChannelAccountItem {
  webhook_verify_token: string | null;
}

// Para dropdowns/filtros (selección de canal en el inbox). Lista CRUDA (sin envelope).
export interface ChannelAccountOption {
  id: string;
  name: string;
  channel_type: ChannelType;
  external_identifier: string;
}

export interface ChannelAccountCreatePayload {
  channel_type: ChannelType;
  name: string;
  external_identifier: string;
  secret_name?: string | null; // nombre del secreto en Secret Manager (NO el valor)
  webhook_verify_token?: string | null;
  phone_number_id?: string | null;
  // bot_configuration_id / default_campaign_id NO se exponen en el create del MVP
  // (módulos no existen); quedan null.
}

export interface ChannelAccountUpdatePayload {
  name?: string;
  external_identifier?: string;
  secret_name?: string | null;
  webhook_verify_token?: string | null;
  phone_number_id?: string | null;
  active?: boolean;
  // channel_type NO se edita (define la cuenta; cambiar de canal = cuenta nueva).
}

// ── Subsets denormalizados embebidos en Conversation/Message ──

// Persona denormalizada (subset, vía batch map de crm — README reconciliación §4:
// shape de `crm.schemas.person.PersonOption`, poblado por `person_option_map`).
// null en la ventana corta antes de resolver (en práctica siempre poblado tras
// find_or_create). El front define aquí el subset que el backend embebe.
export interface ConversationPersonRef {
  id: string;
  full_name: string;
  primary_identifier: ConversationContactIdentifier | null;
}

// Contacto principal embebido (ícono de canal + valor).
export interface ConversationContactIdentifier {
  channel_type: ChannelType;
  identifier: string;
  verified: boolean;
}

// ── Conversation ────────────────────────────────────────

// Fila del inbox. Optimizada para la lista (person/canal/assignee denormalizados
// vía batch maps de crm/admin, sin N+1). NINGUNO de los denormalizados está en
// ALLOWED_FIELDS → NO server-sortable/filterable (lección cd10c78). Filtros de
// estado/canal/asignación = deep-link traducido a FilterCondition sobre columnas
// REALES (status, channel_account_id, assignee_user_id, assignee_type); búsqueda
// por nombre/identificador = client-side sobre la página visible.
export interface ConversationListItem {
  id: string;
  channel_account: ChannelAccountOption;
  person: ConversationPersonRef | null;
  status: ConversationStatus;
  assignee_type: AssigneeType;
  assignee_user: UserAuditInfo | null; // null si bot/unassigned
  last_message_preview: string | null; // primeros 255 chars del último mensaje
  last_message_at: string | null; // timestamptz ISO 8601 (denormalizado; sort real)
  unread_count: number; // incrementa por inbound; resetea en mark-read/take
  created_on: string;
}

// Detalle = ListItem + campos del hilo + el historial de handoff. El listado de
// mensajes NO viaja inflando el detalle (se pide por POST /{id}/messages/list).
export interface ConversationDetail extends ConversationListItem {
  bot_configuration_id: string | null; // forward FK (varchar opaco; hoy null)
  opened_at: string; // timestamptz ISO 8601
  closed_at: string | null;
  assignment_history: ConversationAssignmentLogItem[];
}

// ── Message ─────────────────────────────────────────────

// Mensaje (audit inmutable; SIN soft-delete en backend). attachments inline.
export interface MessageItem {
  id: string;
  conversation_id: string;
  direction: MessageDirection;
  sender_type: SenderType;
  sender_user: UserAuditInfo | null; // null salvo sender_type='advisor'
  content_type: ContentType;
  content: string | null; // texto / transcripción / cuerpo del system_notification
  external_id: string | null; // wamid (WA) — idempotencia
  external_status: MessageExternalStatus | string | null; // last status del provider (varchar libre)
  sent_at: string; // timestamptz ISO 8601
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  failure_reason: string | null;
  attachments: MessageAttachmentItem[]; // [] en el MVP (texto primero)
  created_on: string;
}

// ── MessageAttachment (modelado; processing diferido F4) ──

export interface MessageAttachmentItem {
  id: string;
  message_id: string;
  attachment_type: AttachmentType;
  url: string | null; // decisión de storage en F4 (lazy proxy vs GCS); hoy null
  mime_type: string | null;
  size_bytes: number | null;
  duration_sec: number | null;
  latitude: number | null; // location
  longitude: number | null;
  address_label: string | null;
  original_filename: string | null;
  external_media_id: string | null; // id del medio en el provider
  metadata: Record<string, unknown> | null; // JSONB
  created_on: string;
}

// ── ConversationAssignmentLog (audit inmutable de handoff) ──

export interface ConversationAssignmentLogItem {
  id: string;
  conversation_id: string;
  from_assignee_type: AssigneeType | null; // null en el primer log
  from_assignee_user: UserAuditInfo | null;
  to_assignee_type: AssigneeType;
  to_assignee_user: UserAuditInfo | null;
  started_at: string; // timestamptz ISO 8601
  ended_at: string | null; // null = vigente
  by_actor_user: UserAuditInfo | null; // null = automático (sistema)
  reason: string | null;
}

// ── Request bodies (acciones) ───────────────────────────

// Enviar outbound. MVP solo text → el backend rechaza otros content_type con
// UNSUPPORTED_CONTENT_TYPE (400); el Zod lo previene en español.
export interface MessageSendRequest {
  content: string;
  content_type?: ContentType; // default "text"; MVP solo "text"
}

// Tomar la conversación (assignee = actor). reason opcional (queda en el log).
export interface TakeConversationRequest {
  reason?: string | null;
}

// Liberar: a quién pasa. En el MVP solo `unassigned` (bots no existe → no hay
// "bot"; release a `advisor` → INVALID_ASSIGNEE, para asignar a un asesor se usa
// take — README reconciliación §8). to_bot_configuration_id solo si bot (no MVP).
export interface ReleaseConversationRequest {
  to_assignee_type: AssigneeType;
  to_bot_configuration_id?: string | null;
  reason?: string | null;
}

// Re-exporta ChannelType para quien quiera el alias desde este módulo (single
// source of truth en crm — NO se redefinen los 8 valores; solo se re-exporta).
export type { ChannelType } from "./crm.types";
