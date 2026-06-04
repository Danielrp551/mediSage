/**
 * Espejo TS de los Pydantic schemas del módulo `bots` (#6) — ver
 * `docs/modules/bots/{README,backend,ui,frontend}.md` como fuente de verdad,
 * + ADR-005 (engine-agnostic) y ADR-012 (Cloud Tasks dispatch). Importable
 * desde server actions y client components. Reusa `UserAuditInfo` de
 * `audit.types` — NO se redefine.
 *
 * Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume todavía. Las
 * pantallas llegan por fases: Configuraciones + Versiones (F1), Tools + editor
 * M:N (F2), Depuración por conversación (state + eventos + tool calls, F3).
 *
 * Notas de contrato que el código no expresa solo:
 * - El SECRETO del proveedor NUNCA viaja al front. Las API keys son globales
 *   por entorno (Settings backend); no hay campo de key por bot en el MVP.
 * - `cost_estimated_usd` es `numeric(10,6)` en Postgres → llega como **string**
 *   (Pydantic serializa Decimal como string para no perder precisión).
 * - `input_message_id` / `output_message_id` son el `mid` (doc-id de Firestore,
 *   ADR-011), NO FKs → `string | null`.
 * - Editar prompt/params NO es in-place: crea una NUEVA versión; la promoción es
 *   vía `activate-version`. `is_current` (derivado) = la versión vigente del bot.
 */

import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de bots/enums.py; valores EXACTOS) ─────────────────

// Tipo de bot (rol funcional). MVP no rutea por tipo (eso es futuro); es taxonomía.
export type BotType = "preventa" | "postventa" | "general" | "custom";
export const BOT_TYPES: readonly BotType[] = [
  "preventa",
  "postventa",
  "general",
  "custom",
] as const;

// Proveedor del motor. MVP implementa openai (default) + claude; el resto está en
// el contrato pero el runtime responde PROVIDER_NOT_SUPPORTED hasta que tenga adaptador.
export type BotProvider = "openai" | "claude" | "vertex_ai" | "azure_openai" | "external_webhook";
export const BOT_PROVIDERS: readonly BotProvider[] = [
  "openai",
  "claude",
  "vertex_ai",
  "azure_openai",
  "external_webhook",
] as const;

// Tipo de evento de un turno del bot (traza inmutable).
export type BotEventType =
  | "turn_started"
  | "turn_completed"
  | "turn_failed"
  | "tool_dispatched"
  | "handoff_triggered";
export const BOT_EVENT_TYPES: readonly BotEventType[] = [
  "turn_started",
  "turn_completed",
  "turn_failed",
  "tool_dispatched",
  "handoff_triggered",
] as const;

// Estado de una invocación de tool.
export type ToolCallStatus = "pending" | "success" | "error" | "timeout";
export const TOOL_CALL_STATUSES: readonly ToolCallStatus[] = [
  "pending",
  "success",
  "error",
  "timeout",
] as const;

// ── BotConfiguration ─────────────────────────────────────

// Fila de listado (tabla de Configuraciones). `current_version_number` es derivado
// server-side (el `version` de la versión vigente; null = bot sin versión, no usable).
export interface BotConfigurationItem {
  id: string;
  code: string; // slug UNIQUE ("preventa", "postventa_dental")
  name: string;
  bot_type: BotType;
  description: string | null;
  current_version_id: string | null; // FK→version vigente (null = no usable)
  current_version_number: number | null; // derivado: version de la vigente
  version_count: number; // derivado: cuántas versiones vivas tiene
  max_turns_per_conversation: number | null; // guard opcional (null = sin límite)
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + la versión vigente expandida (si la hay) + los tools M:N (F2).
export interface BotConfigurationDetail extends BotConfigurationItem {
  current_version: BotConfigurationVersionItem | null;
  tool_ids: string[]; // M:N — en F1 siempre []
}

// Para dropdowns (selección de bot a asignar a un canal/conversación). Lista CRUDA.
export interface BotConfigurationOption {
  id: string;
  code: string;
  name: string;
  bot_type: BotType;
}

// Input de creación. `code` se fija al crear; el resto es editable luego.
export interface BotConfigurationCreate {
  code: string;
  name: string;
  bot_type: BotType;
  description?: string | null;
  max_turns_per_conversation?: number | null;
}

// Input de update (PUT parcial). Todos opcionales; `code` es inmutable en la UI (no se reenvía).
// Espeja el Pydantic BotConfigurationUpdate (todos opcionales + `active`) y el Zod
// botConfigurationUpdateSchema.
export interface BotConfigurationUpdate {
  name?: string;
  bot_type?: BotType;
  description?: string | null;
  max_turns_per_conversation?: number | null;
  active?: boolean;
}

// ── BotConfigurationVersion ──────────────────────────────

// Fila de la tab Versiones. `is_current` derivado = (id === config.current_version_id).
// Las versiones son INMUTABLES: el backend NO devuelve campos updated_* ni `active`
// (el soft-disable de la versión viaja como `is_active`).
export interface BotConfigurationVersionItem {
  id: string;
  bot_configuration_id: string;
  version: number; // UNIQUE (bot_configuration_id, version); el service asigna max+1
  provider: BotProvider;
  model_name: string; // default "gpt-4.1-mini"
  is_active: boolean; // soft-disable de la versión (distinto de current)
  is_current: boolean; // derivado: es la versión vigente del bot
  notes: string | null; // changelog del prompt
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
}

// Detalle = Item + el prompt, params y los campos de webhook externo (diferidos).
export interface BotConfigurationVersionDetail extends BotConfigurationVersionItem {
  system_prompt: string;
  parameters: Record<string, unknown>; // {temperature?, max_tokens?, top_p?, ...}
  external_webhook_url: string | null; // solo provider='external_webhook' (DIFERIDO)
  external_webhook_secret_name: string | null; // nombre del secreto, NO el valor (DIFERIDO)
}

// Input para crear una NUEVA versión (editar prompt/params = nueva versión, no in-place).
export interface BotConfigurationVersionCreate {
  system_prompt: string;
  provider: BotProvider;
  model_name: string;
  parameters?: Record<string, unknown> | null;
  external_webhook_url?: string | null;
  external_webhook_secret_name?: string | null;
  notes?: string | null;
}

// Promoción de una versión a vigente. El (id, vid) van por path → body vacío.
export type ActivateVersionRequest = Record<string, never>;

// ── BotTool (catálogo de funciones invocables) ───────────

export interface BotToolItem {
  id: string;
  code: string; // UNIQUE ("list_verticals", "set_lead_status")
  name: string;
  description: string; // la lee el LLM para decidir cuándo invocar
  target_service: string; // "<module>.<service>.<function>" (resuelto por TOOL_REGISTRY)
  requires_confirmation: boolean;
  is_active: boolean;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + el JSON Schema de parámetros (subset común OpenAI/Anthropic).
export interface BotToolDetail extends BotToolItem {
  parameters_schema: Record<string, unknown>; // JSON Schema
}

// Para el editor M:N (multiselect de tools por bot).
export interface BotToolOption {
  id: string;
  code: string;
  name: string;
}

export interface BotToolCreate {
  code: string;
  name: string;
  description: string;
  parameters_schema: Record<string, unknown>;
  target_service: string;
  requires_confirmation?: boolean;
}

export interface BotToolUpdate {
  name: string;
  description: string;
  parameters_schema: Record<string, unknown>;
  target_service: string;
  requires_confirmation?: boolean;
}

// Bulk M:N: qué tools puede usar un bot. PUT /configurations/{id}/tools.
export interface ConfigurationToolsUpdate {
  tool_ids: string[];
}

// ── ConversationBotState (panel de depuración, read-only) ─

export interface ConversationBotState {
  id: string;
  conversation_id: string; // UNIQUE
  bot_configuration_id: string;
  bot_configuration_version_id: string; // versión con la que arrancó (no migra al promover)
  current_intent: string | null;
  collected_slots: Record<string, unknown>; // schema libre por bot
  last_node: string | null;
  last_bot_turn_at: string | null;
  turn_count: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Reset explícito del estado del bot en una conversación. Body vacío (cid por path).
export type ResetBotStateRequest = Record<string, never>;

// ── BotEvent (traza por turno, inmutable, read-only) ─────

export interface BotEventItem {
  id: string;
  conversation_id: string;
  bot_configuration_id: string;
  bot_configuration_version_id: string;
  turn_number: number; // UNIQUE (conversation_id, turn_number)
  event_type: BotEventType;
  input_message_id: string | null; // mid Firestore del inbound que disparó el turno (NO FK)
  output_message_id: string | null; // mid Firestore del outbound emitido (NO FK)
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  cost_estimated_usd: string | null; // numeric(10,6) serializado como string
  error: string | null;
  metadata: Record<string, unknown> | null; // raw provider response/fingerprint (JSONB)
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// ── BotToolCall (traza por invocación de tool, inmutable, read-only) ─

export interface BotToolCallItem {
  id: string;
  conversation_id: string;
  bot_event_id: string | null;
  bot_tool_id: string;
  bot_tool_code: string | null; // derivado: el code del BotTool (para mostrar sin join extra)
  tool_use_id: string | null; // id del tool_use del LLM (matching multi-tool)
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  status: ToolCallStatus;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  latency_ms: number | null;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// ── Engine dispatch ──────────────────────────────────────

// Dispatch MANUAL (debugging por admin, gated BOT_ENGINE_INVOKE). El dispatch
// automático lo hace Cloud Tasks contra `/engine/dispatch` (interno, sin RBAC).
export interface DispatchManualRequest {
  conversation_id: string;
  input_message_id?: string | null;
}
