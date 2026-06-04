# Módulo `bots` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-06-04
> **Audiencia**: developer implementando `frontend/src/.../bots/`.

> **Contrato autoritativo**: este doc respeta la **spec compartida de `bots`** (`C:/tmp/bots_spec.md`, consolidada en [`README.md`](./README.md)) — nombres de entidades, campos, endpoints, permisos, enums y códigos de error son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, manda la spec. **Decisiones confirmadas con el usuario 2026-06-04** (spec §0) — NO re-litigar.

> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), y como **molde directo** el frontend de [`../conversations/frontend.md`](../conversations/frontend.md) (módulo #5 completo en prod, del que `bots` copia patrones — el **panel de depuración** de bots es análogo al **hilo/timeline** de conversations + crm; el **editor M:N de tools** copia el `StatusMatrixEditor`/`SearchableOptionList` de [`../crm/frontend.md`](../crm/frontend.md)). [`../staff/frontend.md`](../staff/frontend.md) es el molde de CRUD/detalle con sub-recursos (la lección `cd10c78`).

> **Posición del módulo** (spec §1): `bots` es el **#6** (catalog→clinic→staff→crm **COMPLETOS en prod**; conversations #5 **human-inbox MVP completo**; sigue bots #6; luego scheduling #7, marketing #8). Es **el cerebro** que atiende automáticamente las conversaciones cuando `Conversation.assignee_type='bot'`. Depende de `conversations` (pipe + Firestore + outbound), `crm` (resolver/transicionar lead, notas), `catalog` (productos), `admin` (audit+RBAC). El frontend de `bots` **NO toca el turno del bot** (eso corre server-side, disparado por Cloud Tasks → `POST /engine/dispatch` con OIDC, sin RBAC) — consume los **endpoints autenticados** `/api/v1/bots/*` para **configurar** bots/tools y **depurar** (read-only) el estado/eventos/tool-calls por conversación.

> **Decisiones de diseño confirmadas** (spec §0, NO re-litigar — distinguen el diseño viejo 2026-05-28 de la realidad actual):
> 1. **Async del turno = Cloud Tasks** (NO BackgroundTasks, NO síncrono): el webhook de conversations encola una Cloud Task; un endpoint interno `POST /api/v1/bots/engine/dispatch` (OIDC, sin RBAC) corre el turno. **El frontend NO ve este flujo** — solo el `POST /engine/dispatch-manual` (gated `BOT_ENGINE_INVOKE`, para debugging del admin).
> 2. **Motor = Embedded multi-proveedor** (OpenAI default `gpt-4.1-mini` + Claude + extensible; adaptadores por provider). **`ExternalBotEngine` DISEÑADO pero DIFERIDO**: las entidades llevan `provider/external_webhook_url/external_webhook_secret_name` (tipos TS presentes), pero el código del engine externo y los endpoints `/engine/external/*` **NO** existen en el MVP. El front muestra `external_webhook` en el select de provider pero lo marca "(no disponible aún)" y deja los campos webhook visibles solo si se elige ese provider.
> 3. **Mensajes en Firestore (CQRS, ADR-011), NO Postgres**: NO hay tabla `message`. `BotEvent.input_message_id`/`output_message_id` son **`string | null` (el `mid` = doc-id Firestore)**, NO FK→message. El front los muestra como referencias opacas (el mensaje vive en el hilo de conversations, no en bots).
> 4. **Tools MVP = crm + catalog SOLO** (scheduling #7 no existe). `book_appointment`/`check_availability` están DISEÑADAS en la doc pero **NO se seedean** — el front NO asume que existen en el catálogo de tools.
> 5. **Credenciales de proveedor globales por entorno** (`Settings.OPENAI_API_KEY`/`ANTHROPIC_API_KEY`): **NO** hay campo de API key en ningún form del front (a diferencia del `secret_name` per-canal de conversations — acá la credencial es global, vía `--set-secrets` de Cloud Run, fuera de la UI).
> 6. **Guards de costo/seguridad**: `MAX_TOOL_ITERATIONS_PER_TURN` (default 5, env del backend — NO en la UI); `BotConfiguration.max_turns_per_conversation` (nullable, **SÍ** editable en el drawer = guard opcional por bot).

> **Convenciones heredadas de catalog/clinic/staff/crm/conversations shipped** (el lector debe tenerlas presentes desde ya):
> 1. **Verbos HTTP**: updates completos usan **`PUT`** (no `PATCH`). En bots: `PUT /configurations/{id}`, `PUT /tools/{id}`, `PUT /configurations/{id}/tools` (bulk M:N). Las **acciones** (crear versión, activar versión, reset state, dispatch-manual) son `POST`.
> 2. **Dropdowns/listas planas de activos** = endpoint **`/active`** (lista CRUDA, `response_model=list[...]`, sin envelope `SingleResponse`). En bots: `GET /configurations/active` → `BotConfigurationOption[]`, `GET /tools` (catálogo) tiene su `/active` análogo para el multiselect de tools por bot (confirmar con backend.md si el M:N usa `/tools/active` o reusa el `list`).
> 3. **Listados paginados** = `POST /<recurso>/list` con `QueryRequest`. En bots: `/configurations/list`, `/tools/list`.
> 4. **Lección hotfix `cd10c78` de staff** (crítica): `defaultSort`, columnas `isSortable` y `searchFields` **SOLO** sobre columnas reales de `ALLOWED_FIELDS`. Ordenar/filtrar server-side por un denormalizado (ej. `current_version` derivado, `bot_type` label) que NO esté whitelistado devuelve **400 → error boundary del RSC**. `defaultSort` de configuration = `created_on desc` (columna real — spec §6). Búsqueda por nombre/código = **client-side** si no están whitelistadas; deep-links por `*_id` traducidos a filtros sobre columnas reales.

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── bots.types.ts                       ← BotConfiguration{Item,Detail,Option,Create,Update},
│                                              BotConfigurationVersion{Item,Create},
│                                              BotTool{Item,Detail,Create,Update,Option},
│                                              ConversationBotState{Item}, BotEvent{Item},
│                                              BotToolCall{Item}, enums TS (BotType/BotProvider/
│                                              BotEventType/ToolCallStatus), ActivateVersionRequest,
│                                              ResetBotStateRequest, SetBotToolsRequest.
│                                              REUSA UserAuditInfo de audit.types.
├── lib/
│   ├── schemas/
│   │   ├── bot-configuration.schema.ts     ← botConfigurationCreate/Update (code/name/bot_type
│   │   │                                      enum/description/max_turns_per_conversation?)
│   │   ├── bot-configuration-version.schema.ts ← botVersionCreate (system_prompt no-vacío + provider
│   │   │                                      enum + model_name + parameters [JSON parseable] +
│   │   │                                      external_webhook_url? si provider=external_webhook)
│   │   └── bot-tool.schema.ts              ← botToolCreate/Update (code/name/description/
│   │                                          parameters_schema [JSON Schema parseable]/
│   │                                          target_service/requires_confirmation/is_active)
│   └── constants/
│       ├── endpoints.ts                    ← EXTEND con bloque BOTS_API (CONFIGURATIONS,
│       │                                      VERSIONS, TOOLS, BOT_STATE/EVENTS/TOOL_CALLS, ENGINE)
│       ├── navigation.ts                   ← EXTEND con grupo 'Bots' (MENU-BOTS)
│       └── bots.ts                         ← NUEVO: BOT_TYPE_META, BOT_PROVIDER_META,
│                                              BOT_EVENT_TYPE_META, TOOL_CALL_STATUS_META,
│                                              PROVIDER_MODEL_PRESETS (ícono + label ES + color)
├── actions/
│   ├── bot-configuration.actions.ts        ← list/active/get/create/update/delete +
│   │                                          listVersions/getVersion/createVersion/activateVersion +
│   │                                          getBotTools/setBotTools (M:N) (tags bots:configurations,
│   │                                          bots:versions:{id}, bots:config-tools:{id})
│   ├── bot-tool.actions.ts                 ← list/active/create/update/delete (tag bots:tools)
│   └── bot-debug.actions.ts               ← getState/resetState/listEvents/listToolCalls +
│                                              dispatchManual (tags bots:debug:{conversationId})
└── app/(main)/bots/
    ├── configuraciones/
    │   ├── page.tsx                        ← RSC prefetch (BotConfiguration list) — molde Verticals
    │   └── _components/
    │       ├── BotConfigurationsClient.tsx ← DataTable + RowActions
    │       ├── BotConfigurationDrawer.tsx  ← create/edit (code/name/bot_type/description/max_turns)
    │       ├── BotVersionsPanel.tsx        ← tab/sección Versiones: lista + "Nueva versión" + Activar
    │       ├── BotVersionEditor.tsx        ← editor de versión (system_prompt textarea grande +
    │       │                                  provider/model selects + JSON editor de parameters)
    │       └── BotToolsAssignment.tsx      ← editor M:N de tools del bot (multiselect, molde
    │                                          StatusMatrixEditor/SearchableOptionList)
    ├── tools/
    │   ├── page.tsx                        ← RSC prefetch (BotTool list) — catálogo de tools
    │   └── _components/
    │       ├── BotToolsClient.tsx          ← DataTable + RowActions
    │       └── BotToolDrawer.tsx           ← create/edit (code/name/description/target_service/
    │                                          parameters_schema [JSON editor]/requires_confirmation)
    └── depuracion/                          ← panel read-only de depuración por conversación
        ├── page.tsx                        ← RSC: selector/deep-link ?c=<conversationId>
        └── _components/
            ├── BotDebugShell.tsx           ← orquesta state + events + tool-calls de una conversación
            ├── BotStateCard.tsx            ← ConversationBotState (intent/slots/turn_count/versión)
            ├── BotEventTimeline.tsx        ← timeline de BotEvent (tokens/latencia/costo/error por turno)
            ├── BotEventRow.tsx             ← fila/tarjeta memoizada de un BotEvent
            └── BotToolCallList.tsx         ← BotToolCall (args/result/status) — read-only, JSON viewer
```

> **Componente JSON editor reusable** (`parameters_schema` del tool, `parameters` de la versión): un textarea controlado con parse/validate en cliente (ver [Editor de JSON](#editor-de-json-parameters_schema--parameters)). NO se introduce una librería de editor de código (Monaco/CodeMirror) en el MVP — un `<textarea>` Fluent monoespaciado + validación `JSON.parse` alcanza (anotado como mejora futura). Vive como helper local (`_components/JsonField.tsx`) o se inlinea en cada drawer/editor; documentar dónde si se promueve a `components/ui/`.

> **Por qué `depuracion` ES una ruta propia** (a diferencia del hilo de conversations, que vive en `?c=` dentro del inbox): el panel de depuración del bot es una **vista de soporte/diagnóstico** independiente, no parte de un inbox 2-paneles. Toma la conversación por **deep-link `?c=<conversationId>`** (se entra desde el inbox de conversations vía un link "Ver actividad del bot", o desde la config del bot). Es read-only (no muta nada salvo `reset state`, gated `BOT_STATE_WRITE`). La conversación seleccionada vive en el URL state (`?c=`), igual que el `?tab=` del detalle de Person en crm — pero la **ruta** `bots/depuracion` sí existe en `NAV_ITEMS` (gated `MENU-BOTS` + `BOT_STATE_READ`).

> **Por qué NO hay `bots/layout.tsx`**: igual que catalog/clinic/staff/crm/conversations — `configuraciones`, `tools`, `depuracion` son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El detalle de una configuración (versiones + tools) NO es una sub-ruta — vive en el **drawer/tabs** de la configuración seleccionada (mismo criterio que Office/Doctor con sub-recursos en staff).

> **Sobre `loading.tsx`**: catalog/clinic/staff/crm/conversations shipped **no** incluyeron `loading.tsx` (el `DataTable` ya renderiza su skeleton vía `isLoading`). `bots` sigue ese criterio en `configuraciones` y `tools`. Para `depuracion`, el primer paint viene del prefetch RSC (state + events de la conversación deep-linkeada, si hay `?c=`) o de un estado vacío "Selecciona una conversación para depurar". No se crean `loading.tsx`.

## Tipos TS — `types/bots.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic) y spec §2). Importable desde server actions y client components. **Reusa** `UserAuditInfo` de `audit.types.ts` — NO se redefine. **NO depende** de otros módulos de dominio: las columnas forward (`conversation_id`, `bot_event_id`, `bot_tool_id`, etc.) son `string` opacos; `input_message_id`/`output_message_id` son **`string | null`** (el `mid` = doc-id Firestore, NO FK — spec §0.3).

```ts
import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de bots/enums.py; valores EXACTOS) ─────────

// Tipo de bot (categoría de negocio). Texto libre del catálogo de bots.
export type BotType = "preventa" | "postventa" | "general" | "custom";
export const BOT_TYPES: readonly BotType[] = ["preventa", "postventa", "general", "custom"] as const;

// Proveedor del motor de la versión. MVP implementa openai (default) + claude;
// el resto está en el contrato pero da PROVIDER_NOT_SUPPORTED (400) en runtime;
// external_webhook está DISEÑADO pero DIFERIDO (sin engine ni endpoints en el MVP).
export type BotProvider =
  | "openai"
  | "claude"
  | "vertex_ai"
  | "azure_openai"
  | "external_webhook";
export const BOT_PROVIDERS: readonly BotProvider[] = [
  "openai",
  "claude",
  "vertex_ai",
  "azure_openai",
  "external_webhook",
] as const;
// Providers REALMENTE soportados en el MVP (el select del editor habilita solo estos;
// los demás se muestran deshabilitados con "(no disponible aún)"). Espeja spec §0.2 / §2.
export const SUPPORTED_BOT_PROVIDERS: readonly BotProvider[] = ["openai", "claude"] as const;

// Tipo de evento del turno (audit del motor). Espeja bots/enums.py.
export type BotEventType =
  | "turn_started"
  | "turn_completed"
  | "turn_failed"
  | "tool_dispatched"
  | "handoff_triggered";

// Estado de una invocación de tool dentro de un turno.
export type ToolCallStatus = "pending" | "success" | "error" | "timeout";

// ── BotConfiguration ────────────────────────────────────

// Fila de listado (tabla de Configuraciones) — espeja BotConfigurationItem del backend.
// current_version es un subset derivado (el número de versión vigente + su id) para
// mostrar "v3 (vigente)" sin pedir el detalle. NINGÚN derivado es server-sortable
// salvo lo whitelistado en ALLOWED_FIELDS (spec §6: code/name/bot_type/created_on).
export interface BotConfigurationItem {
  id: string;
  code: string; // slug único (parcial vivo) — "preventa", "postventa_dental"
  name: string;
  bot_type: BotType;
  description: string | null;
  current_version_id: string | null; // null = sin versión vigente, NO usable
  current_version_number: number | null; // derivado (el `version` de la versión vigente)
  max_turns_per_conversation: number | null; // guard opcional (null = sin límite)
  active: boolean;
  created_on: string; // timestamptz ISO 8601
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + las versiones embebidas (lista) + los tools asignados (M:N).
// El system_prompt/params NO viajan inflando el detalle de la config — viven en cada
// BotConfigurationVersion (se piden por el sub-recurso de versiones).
export interface BotConfigurationDetail extends BotConfigurationItem {
  versions: BotConfigurationVersionItem[]; // historial de versiones (resumen por versión)
  tools: BotToolOption[]; // tools asignados al bot (M:N) — para el editor de asignación
}

// Para dropdowns/filtros (selección de bot). Lista CRUDA (sin envelope).
export interface BotConfigurationOption {
  id: string;
  code: string;
  name: string;
  bot_type: BotType;
}

export interface BotConfigurationCreatePayload {
  code: string;
  name: string;
  bot_type: BotType;
  description?: string | null;
  max_turns_per_conversation?: number | null;
}

export interface BotConfigurationUpdatePayload {
  name?: string;
  bot_type?: BotType;
  description?: string | null;
  max_turns_per_conversation?: number | null;
  active?: boolean;
  // code NO se edita (slug estable; espeja el backend, que no lo permite en update).
  // current_version_id NO se setea por update — se promueve vía activate-version.
}

// ── BotConfigurationVersion ─────────────────────────────

// Fila de la lista de versiones (panel Versiones). Espeja BotConfigurationVersionItem.
// El system_prompt completo puede venir o no en el Item (puede ser pesado); si el
// backend lo recorta, el Item trae un preview y el detalle/editor trae el completo —
// confirmar con backend.md. Aquí lo incluyo completo (el editor lo necesita al re-abrir).
export interface BotConfigurationVersionItem {
  id: string;
  bot_configuration_id: string;
  version: number; // UNIQUE (bot_configuration_id, version); el backend asigna max+1
  system_prompt: string;
  provider: BotProvider;
  model_name: string; // default "gpt-4.1-mini" (texto libre; depende del provider)
  parameters: Record<string, unknown>; // {temperature?, max_tokens?, top_p?, ...} (schema libre)
  external_webhook_url: string | null; // solo provider=external_webhook (DIFERIDO)
  external_webhook_secret_name: string | null; // DIFERIDO
  notes: string | null; // changelog del prompt
  is_active: boolean; // soft-disable de la versión (distinto de "vigente")
  is_current: boolean; // derivado: = (bot_configuration.current_version_id == this.id)
  created_on: string; // timestamptz ISO 8601
  created_by: string;
  created_by_user: UserAuditInfo | null;
}

// Crear una versión NUEVA (editar prompt/params = nueva versión, NO in-place — spec §2).
// El backend asigna `version = max+1`; el front NO lo manda.
export interface BotConfigurationVersionCreatePayload {
  system_prompt: string;
  provider: BotProvider;
  model_name: string;
  parameters?: Record<string, unknown> | null; // default {} si no se envía
  external_webhook_url?: string | null; // requerido si provider=external_webhook (EXTERNAL_WEBHOOK_URL_REQUIRED 400)
  external_webhook_secret_name?: string | null;
  notes?: string | null;
}

// ── BotTool ─────────────────────────────────────────────

// Fila del catálogo de tools. Espeja BotToolItem.
export interface BotToolItem {
  id: string;
  code: string; // slug único (parcial vivo) — "list_verticals", "set_lead_status"
  name: string;
  description: string; // la usa el LLM para decidir cuándo invocar
  target_service: string; // "<module>.<service>.<function>" resuelto por TOOL_REGISTRY
  requires_confirmation: boolean;
  is_active: boolean;
  active: boolean; // ActiveMixin (toggle de negocio) — distinto de is_active del tool
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + el JSON Schema de parámetros (pesado, no viaja en el Item de la tabla).
export interface BotToolDetail extends BotToolItem {
  parameters_schema: Record<string, unknown>; // JSON Schema (subset común OpenAI/Anthropic)
}

// Para el multiselect de tools por bot (M:N) y dropdowns. Lista CRUDA.
export interface BotToolOption {
  id: string;
  code: string;
  name: string;
  requires_confirmation: boolean;
}

export interface BotToolCreatePayload {
  code: string;
  name: string;
  description: string;
  parameters_schema: Record<string, unknown>; // JSON Schema validado en cliente como JSON parseable
  target_service: string;
  requires_confirmation?: boolean; // default false
  is_active?: boolean; // default true
}

export interface BotToolUpdatePayload {
  name?: string;
  description?: string;
  parameters_schema?: Record<string, unknown>;
  target_service?: string;
  requires_confirmation?: boolean;
  is_active?: boolean;
  active?: boolean;
  // code NO se edita (slug estable).
}

// ── ConversationBotState (depuración; read-only) ────────

export interface ConversationBotStateItem {
  id: string;
  conversation_id: string; // UNIQUE — una fila de estado por conversación
  bot_configuration_id: string;
  bot_configuration_version_id: string; // versión con la que arrancó (NO migra al promover)
  current_intent: string | null;
  collected_slots: Record<string, unknown>; // schema libre por bot
  last_node: string | null;
  last_bot_turn_at: string | null; // timestamptz ISO 8601
  turn_count: number;
  active: boolean;
  created_on: string;
  updated_on: string;
}

// ── BotEvent (depuración; read-only; audit inmutable, SIN soft-delete) ──

export interface BotEventItem {
  id: string;
  conversation_id: string;
  bot_configuration_id: string;
  bot_configuration_version_id: string;
  turn_number: number; // UNIQUE (conversation_id, turn_number)
  event_type: BotEventType;
  // input_message_id/output_message_id = el `mid` (doc-id Firestore), NO FK→message
  // (spec §0.3). string | null. El front los muestra como referencia opaca al hilo.
  input_message_id: string | null;
  output_message_id: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  cost_estimated_usd: string | null; // numeric(10,6) → string para no perder precisión
  error: string | null;
  metadata: Record<string, unknown> | null; // raw provider response/fingerprint
  created_on: string; // timestamptz ISO 8601
}

// ── BotToolCall (depuración; read-only; audit inmutable, SIN soft-delete) ──

export interface BotToolCallItem {
  id: string;
  conversation_id: string;
  bot_event_id: string | null; // FK→bot_event (el turno que la disparó)
  bot_tool_id: string;
  bot_tool_code: string | null; // denormalizado (para mostrar el código sin pedir el tool)
  tool_use_id: string | null; // id del tool_use del LLM (matching multi-tool)
  arguments: Record<string, unknown>; // args con que el LLM invocó
  result: Record<string, unknown> | null; // resultado de la tool (null si error/pending)
  status: ToolCallStatus;
  error_message: string | null;
  started_at: string; // timestamptz ISO 8601
  completed_at: string | null;
  latency_ms: number | null;
  created_on: string;
}

// ── Request bodies (acciones) ───────────────────────────

// Activar una versión como la vigente del bot (current_version_id = version_id).
// El path lleva el version_id (POST /configurations/{id}/activate-version/{vid});
// el body puede ir vacío o llevar una confirmación — confirmar con backend.md.
export interface ActivateVersionRequest {
  // vacío en el MVP; el version_id va en el path. Se deja por si el backend pide algo.
}

// Reset del estado del bot en una conversación (borra slots/intent/turn_count;
// el motor arranca de cero en el siguiente turno). Gated BOT_STATE_WRITE.
export interface ResetBotStateRequest {
  reason?: string | null;
}

// Asignar el set de tools de un bot (bulk M:N — reemplaza el set completo).
export interface SetBotToolsRequest {
  tool_ids: string[];
}

// Disparo manual del turno (debugging del admin; encola/dispara dispatch_turn).
// Gated BOT_ENGINE_INVOKE. El body lleva la conversación; input_message_id opcional.
export interface DispatchManualRequest {
  conversation_id: string;
  input_message_id?: string | null;
}
```

> **Nota sobre las clases de tiempo** (igual que clinic/staff/crm/conversations, ver [`../staff/frontend.md`](../staff/frontend.md)): todas las columnas de tiempo de `bots` (`created_on`, `updated_on`, `last_bot_turn_at`, `started_at`, `completed_at`) son `timestamptz` → ISO 8601 con offset → se formatean con `lib/utils/date.ts` (`formatDate` / hora local / relativa). **No hay** fechas `date`-sin-TZ en este módulo. El **timeline de BotEvent** muestra hora local de cada turno y agrupa por día — el cálculo de "Hoy"/"Ayer" es **client-only** (lección TZ recurrente; ver [BotEventTimeline](#boteventtimelinetsx-timeline-de-turnos)).

> **`cost_estimated_usd` es `string`, no `number`** (espeja `numeric(10,6)` del backend): para no perder precisión decimal en la serialización JSON. El front lo parsea con `Number(...)` solo para formatear (ej. `$0.000142`), nunca para acumular sumas client-side sin cuidado. Mismo criterio que cualquier `numeric` de Postgres (mantener como string en el contrato).

> **`input_message_id`/`output_message_id` = `string | null` opacos** (spec §0.3): son el `mid` (doc-id Firestore) del inbound/outbound del turno, **NO** FK a una tabla `message` (no existe — los mensajes viven en Firestore, ADR-011). El front NO los resuelve a un mensaje (no hay endpoint en bots para eso); los muestra como referencia ("Mensaje de entrada: `wamid.HBg…`") con un link opcional al hilo de conversations (`/conversaciones/bandeja?c=<conversation_id>`) si el usuario tiene `CONVERSATIONS_READ`. Anotar en deviations si el link cruzado se difiere.

## Zod schemas

> **Regla del template** ([frontend/CLAUDE.md](../../../frontend/CLAUDE.md)): los Zod viven en `src/lib/schemas/` y los importan **tanto el form (cliente) como el Server Action (server)** → drift imposible. Los mensajes visibles van en **español**; los `path`/nombres de campo en inglés. Validaciones de largo espejan los `varchar(...)` del modelo (spec §2).

### `lib/schemas/bot-configuration.schema.ts`

CRUD del bot (admin). `bot_type` es un **enum cerrado** (`BotType`). `code` es un slug (solo `create`, disabled en `edit`). `max_turns_per_conversation` opcional (null = sin límite); si se setea, entero positivo.

```ts
import { z } from "zod";

import { BOT_TYPES } from "@/types/bots.types";

const botConfigurationBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  bot_type: z.enum(BOT_TYPES, { errorMap: () => ({ message: "Tipo de bot no válido" }) }),
  description: z.string().max(2000, "Máximo 2000 caracteres").nullable().optional().or(z.literal("")),
  // Guard opcional: null/vacío = sin límite. Si se setea, entero ≥ 1.
  max_turns_per_conversation: z
    .number({ invalid_type_error: "Debe ser un número" })
    .int("Debe ser un entero")
    .positive("Debe ser mayor que 0")
    .nullable()
    .optional(),
});

export const botConfigurationCreateSchema = botConfigurationBase.extend({
  // Slug: minúsculas, números, guion bajo (espeja la UNIQUE parcial + convención de code).
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(40, "Máximo 40 caracteres")
    .regex(/^[a-z0-9_]+$/, "Solo minúsculas, números y guion bajo"),
});

export const botConfigurationUpdateSchema = botConfigurationBase.partial().extend({
  active: z.boolean().optional(),
  // code NO se edita (slug estable; el backend no lo permite en update).
});

export type BotConfigurationCreateInput = z.infer<typeof botConfigurationCreateSchema>;
export type BotConfigurationUpdateInput = z.infer<typeof botConfigurationUpdateSchema>;
```

> **Lo que Zod NO puede validar** (queda como error de servidor en español): `BOT_CONFIGURATION_CODE_TAKEN` (409, viola la UNIQUE parcial `code WHERE deleted_at IS NULL` contra BD — el front no conoce los otros bots). Se muestra en `MessageBar` sin cerrar el drawer.

### `lib/schemas/bot-configuration-version.schema.ts`

Crear una versión nueva. `system_prompt` no-vacío (es el corazón del bot). `provider` enum; en el MVP el form ofrece **openai/claude** habilitados y el resto deshabilitado (el schema acepta los 5 para no bloquear futuros, pero `external_webhook` exige `external_webhook_url` vía `superRefine` — espeja `EXTERNAL_WEBHOOK_URL_REQUIRED` 400). `parameters` es un **JSON libre** que el form captura como texto y el schema valida que sea JSON parseable (objeto).

```ts
import { z } from "zod";

import { BOT_PROVIDERS } from "@/types/bots.types";

// Valida que un string sea JSON parseable a OBJETO (no array/escalar). Reusable por el
// parameters de la versión y el parameters_schema del tool. Devuelve el objeto parseado.
const jsonObjectString = (label: string) =>
  z
    .string()
    .trim()
    .transform((raw, ctx) => {
      if (raw === "") return {}; // vacío = objeto vacío (default)
      try {
        const parsed = JSON.parse(raw);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${label} debe ser un objeto JSON` });
          return z.NEVER;
        }
        return parsed as Record<string, unknown>;
      } catch {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${label} no es JSON válido` });
        return z.NEVER;
      }
    });

export const botVersionCreateSchema = z
  .object({
    system_prompt: z.string().min(1, "El prompt no puede estar vacío").max(50_000, "Demasiado largo"),
    provider: z.enum(BOT_PROVIDERS, { errorMap: () => ({ message: "Proveedor no válido" }) }),
    model_name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
    // El form pasa el textarea de JSON crudo; el schema lo transforma a objeto.
    parameters: jsonObjectString("Los parámetros"),
    external_webhook_url: z
      .string()
      .url("URL no válida")
      .max(500, "Máximo 500 caracteres")
      .nullable()
      .optional()
      .or(z.literal("")),
    external_webhook_secret_name: z
      .string()
      .max(255, "Máximo 255 caracteres")
      .nullable()
      .optional()
      .or(z.literal("")),
    notes: z.string().max(2000, "Máximo 2000 caracteres").nullable().optional().or(z.literal("")),
  })
  .superRefine((val, ctx) => {
    // provider=external_webhook ⇒ external_webhook_url requerido (espeja EXTERNAL_WEBHOOK_URL_REQUIRED 400).
    if (val.provider === "external_webhook" && !val.external_webhook_url) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["external_webhook_url"],
        message: "La URL del webhook es obligatoria para el proveedor externo",
      });
    }
  });

export type BotVersionCreateInput = z.infer<typeof botVersionCreateSchema>;
```

> **`provider=external_webhook` está DIFERIDO** (spec §0.2): el schema lo acepta y valida `external_webhook_url`, pero el **engine externo NO existe en el MVP** → si alguien crea una versión con ese provider y la activa, el dispatch dará `PROVIDER_NOT_SUPPORTED` (400) en runtime. El form **deshabilita** la opción `external_webhook` en el select (`SUPPORTED_BOT_PROVIDERS` = openai/claude) y muestra "(no disponible aún)"; los campos `external_webhook_*` solo se muestran si se elige ese provider (que está deshabilitado en el MVP). Los campos están en el schema/tipos para no romper el contrato cuando F4 cablee el engine externo (aditivo, sin migración). Anotar en deviations.

> **`parameters` se captura como texto, se valida como JSON, se envía como objeto**: el editor (`BotVersionEditor`) tiene un `<textarea>` monoespaciado con el JSON; el Zod lo `transform`a a `Record<string, unknown>`. El backend recibe el objeto (`parameters: jsonb`). El form pre-popula el textarea con `JSON.stringify(version.parameters, null, 2)` al re-abrir una versión como base de la siguiente. Ver [Editor de JSON](#editor-de-json-parameters_schema--parameters).

### `lib/schemas/bot-tool.schema.ts`

CRUD del catálogo de tools (admin). `code` slug (solo create). `parameters_schema` = JSON Schema (subset común OpenAI/Anthropic) — el front lo valida solo como **JSON parseable a objeto** (no valida que sea un JSON Schema válido; eso lo hace el LLM/adapter en runtime). `target_service` = `<module>.<service>.<function>` (texto; el backend resuelve contra `TOOL_REGISTRY` → `TOOL_NOT_REGISTERED` 404 en runtime si no está registrado, NO al guardar).

```ts
import { z } from "zod";

const jsonObjectString = (label: string) =>
  z
    .string()
    .trim()
    .transform((raw, ctx) => {
      if (raw === "") return {};
      try {
        const parsed = JSON.parse(raw);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${label} debe ser un objeto JSON` });
          return z.NEVER;
        }
        return parsed as Record<string, unknown>;
      } catch {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${label} no es JSON válido` });
        return z.NEVER;
      }
    });

const botToolBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  // La description la usa el LLM para decidir cuándo invocar la tool → obligatoria + descriptiva.
  description: z.string().min(1, "Obligatorio (la usa el modelo para decidir cuándo invocar)"),
  parameters_schema: jsonObjectString("El esquema de parámetros"),
  // "<module>.<service>.<function>" (ej. "crm.person_lead_status.transition"). No se valida
  // contra el registry en el front (eso es runtime: TOOL_NOT_REGISTERED 404).
  target_service: z
    .string()
    .min(1, "Obligatorio")
    .max(120, "Máximo 120 caracteres")
    .regex(/^[a-z0-9_]+(\.[a-z0-9_]+)+$/, "Formato: modulo.servicio.funcion"),
  requires_confirmation: z.boolean().optional(),
  is_active: z.boolean().optional(),
});

export const botToolCreateSchema = botToolBase.extend({
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(60, "Máximo 60 caracteres")
    .regex(/^[a-z0-9_]+$/, "Solo minúsculas, números y guion bajo"),
});

export const botToolUpdateSchema = botToolBase.partial().extend({
  active: z.boolean().optional(),
  // code NO se edita (slug estable).
});

export type BotToolCreateInput = z.infer<typeof botToolCreateSchema>;
export type BotToolUpdateInput = z.infer<typeof botToolUpdateSchema>;
```

> **El front NO valida que `parameters_schema` sea un JSON Schema válido** (solo que sea JSON parseable a objeto): validar el dialecto JSON Schema completo (draft-07/2020-12) requeriría una librería (`ajv`) y no aporta en el MVP — el adapter del provider y el LLM rechazan un schema malformado en runtime. El front solo previene JSON sintácticamente roto. Anotar como mejora futura (validar el meta-schema con `ajv` en el editor).

> **`requires_confirmation`**: flag del tool que (a futuro) hará que el bot pida confirmación antes de ejecutar tools sensibles (ej. `set_lead_status`). En el MVP el front lo muestra como un Switch en el drawer y un badge en la tabla; la semántica de "confirmar" la implementa el engine (spec §4: `set_lead_status` lleva `requires_confirmation=true`). El front no cablea la confirmación en sí (no hay UI de chat del bot acá — eso vive en el hilo de conversations).

## Constantes de presentación — `lib/constants/bots.ts`

Metadata de presentación: ícono Fluent, label en español y color (token Fluent — **NO** `brandPalette.accent`, que no existe; ver [`ui.md`](./ui.md)). **Nuevo** (bots necesita su propia tabla: tipos de bot, providers, tipos de evento, estados de tool-call).

```ts
import {
  BotRegular,
  WrenchRegular,
  PlayRegular,
  CheckmarkCircleRegular,
  ErrorCircleRegular,
  ClockRegular,
  DismissCircleRegular,
  ArrowRoutingRegular,
  PersonHandshakeRegular,
} from "@fluentui/react-icons";
import { tokens } from "@fluentui/react-components";

import type {
  BotEventType,
  BotProvider,
  BotType,
  ToolCallStatus,
} from "@/types/bots.types";

// ── Tipo de bot (badge en la tabla de configuraciones) ──
export const BOT_TYPE_META: Record<BotType, { label: string; color: string }> = {
  preventa: { label: "Preventa", color: tokens.colorPaletteBlueForeground2 },
  postventa: { label: "Postventa", color: tokens.colorPaletteGreenForeground2 },
  general: { label: "General", color: tokens.colorNeutralForeground2 },
  custom: { label: "Personalizado", color: tokens.colorPalettePurpleForeground2 },
};

// ── Proveedor del motor (select del editor de versiones) ──
// supported = se puede elegir en el MVP. Los no soportados se muestran deshabilitados.
export const BOT_PROVIDER_META: Record<
  BotProvider,
  { label: string; supported: boolean; hint?: string }
> = {
  openai: { label: "OpenAI", supported: true },
  claude: { label: "Claude (Anthropic)", supported: true },
  vertex_ai: { label: "Vertex AI", supported: false, hint: "No disponible aún" },
  azure_openai: { label: "Azure OpenAI", supported: false, hint: "No disponible aún" },
  external_webhook: { label: "Webhook externo", supported: false, hint: "No disponible aún" },
};

// Presets de modelo por provider (el select de modelo ofrece estos + permite texto libre).
// Default global = gpt-4.1-mini (spec §0.2 / §2). El campo es texto libre (model_name varchar).
export const PROVIDER_MODEL_PRESETS: Record<BotProvider, string[]> = {
  openai: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini"],
  claude: ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
  vertex_ai: [],
  azure_openai: [],
  external_webhook: [],
};

// ── Tipo de evento del turno (timeline de depuración) ──
export const BOT_EVENT_TYPE_META: Record<
  BotEventType,
  { label: string; icon: React.FC; color: string }
> = {
  turn_started: { label: "Turno iniciado", icon: PlayRegular, color: tokens.colorNeutralForeground3 },
  turn_completed: { label: "Turno completado", icon: CheckmarkCircleRegular, color: tokens.colorPaletteGreenForeground2 },
  turn_failed: { label: "Turno fallido", icon: ErrorCircleRegular, color: tokens.colorPaletteRedForeground1 },
  tool_dispatched: { label: "Tool ejecutada", icon: WrenchRegular, color: tokens.colorPaletteBlueForeground2 },
  handoff_triggered: { label: "Handoff disparado", icon: PersonHandshakeRegular, color: tokens.colorPaletteYellowForeground2 },
};

// ── Estado de una invocación de tool (lista de tool-calls) ──
export const TOOL_CALL_STATUS_META: Record<
  ToolCallStatus,
  { label: string; icon: React.FC; color: string }
> = {
  pending: { label: "En curso", icon: ClockRegular, color: tokens.colorNeutralForeground3 },
  success: { label: "Éxito", icon: CheckmarkCircleRegular, color: tokens.colorPaletteGreenForeground2 },
  error: { label: "Error", icon: ErrorCircleRegular, color: tokens.colorPaletteRedForeground1 },
  timeout: { label: "Tiempo agotado", icon: DismissCircleRegular, color: tokens.colorPaletteRedForeground1 },
};
```

> **Verificar los íconos en la versión instalada de `@fluentui/react-icons`** (mismo paso que catalog/clinic/staff/crm/conversations): `BotRegular`, `WrenchRegular`, `PlayRegular`, `CheckmarkCircleRegular`, `ErrorCircleRegular`, `ClockRegular`, `DismissCircleRegular`, `ArrowRoutingRegular`, `PersonHandshakeRegular`. Si alguno no resuelve: `BotRegular` → `ChatRegular` (ya verificado en conversations); `WrenchRegular` → `SettingsRegular`/`ToolboxRegular`; `PlayRegular` → `ArrowPlayRegular`; `PersonHandshakeRegular` → `PeopleRegular`/`ArrowRoutingRegular`; `ArrowRoutingRegular` → `BranchRegular`. **No** introducir librerías de íconos nuevas. Documentar el fallback elegido en el `iconMap` del `Sidebar.tsx`.

> **`brandPalette` NO tiene `accent`** (lección operativa transversal): para colores que no sean primary/primaryHover/primaryPressed/primarySelected, usar tokens Fluent semánticos (`tokens.colorPaletteRedForeground1`, `tokens.colorPaletteBlueForeground2`, etc.) como arriba. Los rojos de "fallido"/"error" = `tokens.colorPaletteRedForeground1`; los verdes de "éxito"/"completado" = `tokens.colorPaletteGreenForeground2`.

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque `BOTS` completo (todas las URLs autenticadas de la spec §6). El `POST /engine/dispatch` (top-level interno, OIDC, **sin RBAC** — target de Cloud Tasks) **NO va acá**: lo invoca Cloud Tasks server-to-server, el frontend nunca lo llama (N/A front). El front SÍ tiene `dispatch-manual` (RBAC `BOT_ENGINE_INVOKE`, debugging del admin). Convención: `POST /<recurso>/list`; `PUT` para updates completos; `/active` lista cruda; acciones `POST`.

```ts
const BOTS = "/api/v1/bots"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, CATALOG, CLINIC, STAFF, CRM,
  //   CONVERSATIONS (existentes) …

  // ── Bots module ──────────────────────────────────────────
  BOT_CONFIGURATIONS: {
    LIST: `${BOTS}/configurations/list`, // POST + QueryRequest → PaginatedResponse[BotConfigurationItem]
    CREATE: `${BOTS}/configurations`, // POST
    GET: (id: string) => `${BOTS}/configurations/${id}`, // SingleResponse[BotConfigurationDetail]
    UPDATE: (id: string) => `${BOTS}/configurations/${id}`, // ← PUT
    DELETE: (id: string) => `${BOTS}/configurations/${id}`, // soft delete
    ACTIVE: `${BOTS}/configurations/active`, // raw BotConfigurationOption[] (dropdown)
    // Versiones (sub-recurso de la configuración)
    VERSIONS: (id: string) => `${BOTS}/configurations/${id}/versions`, // GET list / POST create
    VERSION_GET: (id: string, vid: string) => `${BOTS}/configurations/${id}/versions/${vid}`, // GET
    ACTIVATE_VERSION: (id: string, vid: string) =>
      `${BOTS}/configurations/${id}/activate-version/${vid}`, // POST (promueve a vigente)
    // Tools del bot (M:N)
    TOOLS: (id: string) => `${BOTS}/configurations/${id}/tools`, // GET (set actual) / PUT (bulk reemplaza)
  },
  BOT_TOOLS: {
    LIST: `${BOTS}/tools/list`, // POST + QueryRequest → PaginatedResponse[BotToolItem]
    CREATE: `${BOTS}/tools`, // POST
    UPDATE: (id: string) => `${BOTS}/tools/${id}`, // ← PUT
    DELETE: (id: string) => `${BOTS}/tools/${id}`, // soft delete
    ACTIVE: `${BOTS}/tools/active`, // raw BotToolOption[] (multiselect M:N) — confirmar con backend.md
  },
  BOT_DEBUG: {
    // State/Trace por conversación (read-only salvo el reset). cid = conversation_id.
    STATE: (cid: string) => `${BOTS}/conversations/${cid}/state`, // GET → SingleResponse[ConversationBotStateItem | null]
    STATE_RESET: (cid: string) => `${BOTS}/conversations/${cid}/state/reset`, // POST (BOT_STATE_WRITE)
    EVENTS: (cid: string) => `${BOTS}/conversations/${cid}/events`, // GET → events del hilo
    TOOL_CALLS: (cid: string) => `${BOTS}/conversations/${cid}/tool-calls`, // GET → tool-calls del hilo
  },
  BOT_ENGINE: {
    // /engine/dispatch (OIDC, sin RBAC, target de Cloud Tasks) NO está acá — el front no lo llama.
    DISPATCH_MANUAL: `${BOTS}/engine/dispatch-manual`, // POST (BOT_ENGINE_INVOKE) — debugging admin
  },
} as const;
```

> **`/engine/dispatch` (OIDC) NO se expone al front**: lo invoca Cloud Tasks server-to-server con un token OIDC (sin RBAC — spec §6). El frontend nunca lo llama (igual que los webhooks de conversations son top-level sin JWT y no están en `endpoints.ts`). El único path del engine que el front usa es `dispatch-manual` (gated `BOT_ENGINE_INVOKE`), para que un admin dispare/re-dispare un turno manualmente al depurar. `/engine/external/*` está **DIFERIDO** (spec §0.2) — no se declara.

> **`/active` devuelve lista CRUDA** (`response_model=list[...]`, sin envelope) — no se lee `.data`. El resto (`/list`, `GET /{id}`, `POST`, `PUT`, acciones) usa los envelopes del template (`PaginatedResponse` / `SingleResponse`) y se lee con `.data`. El `GET /state` puede devolver `SingleResponse[null]` (la conversación existe pero el bot nunca corrió un turno → sin estado) — el front muestra el estado vacío, no error (mismo criterio que `getLeadStatus` → `T | null` en crm). Confirmar el shape exacto con [`backend.md`](./backend.md#endpoints).

> **`VERSIONS`/`TOOLS` (sub-recursos) usan el mismo path para GET y POST/PUT** (REST): `GET /configurations/{id}/versions` lista; `POST` crea. `GET /configurations/{id}/tools` devuelve el set actual; `PUT` lo reemplaza (bulk M:N `{tool_ids:[]}`). El `endpoints.ts` declara la URL una vez (función `VERSIONS(id)` / `TOOLS(id)`); el verbo lo elige el action.

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `bots` entre `conversations` y `admin` (orden de módulos: catalog→clinic→staff→crm→conversations→**bots**→admin):

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … */ },
  { key: "catalog", /* … */ },
  { key: "clinic", /* … */ },
  { key: "staff", /* … */ },
  { key: "crm", /* … */ },
  { key: "conversations", /* … */ },

  // ── NEW ───────────────────────────────────────────
  {
    key: "bots",
    label: "Bots",
    icon: "BotRegular",
    children: [
      {
        key: "bot-configurations",
        label: "Configuraciones",
        icon: "BotRegular",
        url: "/bots/configuraciones",
        permissions: ["BOT_CONFIGURATIONS_READ"],
      },
      {
        key: "bot-tools",
        label: "Herramientas",
        icon: "WrenchRegular",
        url: "/bots/tools",
        permissions: ["BOT_TOOLS_READ"],
      },
      {
        key: "bot-debug",
        label: "Depuración",
        icon: "BugRegular",
        url: "/bots/depuracion",
        permissions: ["BOT_STATE_READ"],
      },
    ],
  },

  { key: "admin", /* … */ },
];
```

> **Gating del grupo vs items** (spec §5): el grupo "Bots" está gated `MENU-BOTS` (lo tiene ADMIN + ASESOR; DOCTOR no — spec §5). Cada item lleva además su permiso fino: Configuraciones `BOT_CONFIGURATIONS_READ`, Herramientas `BOT_TOOLS_READ`, Depuración `BOT_STATE_READ`. El page RSC valida con `requirePermission(...)`. El **ASESOR** es **read-only**: tiene `BOT_CONFIGURATIONS_READ` + `BOT_STATE_READ` + `BOT_EVENTS_READ` + `BOT_TOOL_CALLS_READ` → ve Configuraciones (sin crear/editar/borrar/versionar) + Depuración, pero **NO** Herramientas (no tiene `BOT_TOOLS_READ` — solo admin gestiona el catálogo de tools, spec §5). El **grupo** se muestra si el usuario tiene alguno de los permisos hijos (el Sidebar colapsa grupos sin hijos visibles); `MENU-BOTS` es el toggle "de entrada". **No** redefinir los 14 permisos aquí — son canónicos en [`../_seed-and-roles.md`](../_seed-and-roles.md) / spec §5.

> **Íconos** (verificar que existan en `@fluentui/react-icons` v9; fallback si no): grupo Bots `BotRegular`, Configuraciones `BotRegular`, Herramientas `WrenchRegular`, Depuración `BugRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que catalog/clinic/staff/crm/conversations). Alternativas verificadas: `BotRegular` → `ChatRegular` (ya usado en conversations); `WrenchRegular` → `SettingsRegular`/`ToolboxRegular`; `BugRegular` → `BeakerRegular`/`WrenchScrewdriverRegular`. **Verificar `BotRegular`** (mencionado en spec §9 como candidato) — conversations ya lo registró para el `ASSIGNEE_TYPE_META.bot`, así que probablemente ya está en el `iconMap`.

> El sidebar (`components/layout/Sidebar/Sidebar.tsx`) ya filtra items por `permissions` vs `useAuth().permissions`. El detalle de una configuración (versiones/tools) NO está en `NAV_ITEMS` (vive en el drawer/tabs de la config seleccionada); la depuración de una conversación vive en `?c=` dentro de `bots/depuracion` — su gating es el del page contenedor.

## Server Actions

Mismo molde que clinic/catalog/staff/crm/conversations: validar con Zod en el action → llamar backend client → `revalidateTag(TAG, "max")`. Reusa el `MutationResult<T>` exportado por `user.actions.ts` (no se redefine). **Next 16 exige el 2º argumento de `revalidateTag`** (`"max"`) — lección del template; omitirlo es error de tipos/runtime.

> **`bots` NO tiene tiempo real ni polling** (a diferencia de conversations): no hay inbox, no hay Firestore listener, no hay `setInterval`. El módulo es **CRUD de configuración** (configuraciones/tools) + **lectura de depuración** (state/events/tool-calls de una conversación, a demanda). El panel de depuración carga los datos al seleccionar una conversación y se **refetcha a demanda** (botón "Actualizar" o `router.refresh()`); opcionalmente puede refrescar tras un `dispatch-manual`. NO se pollea el estado del bot (el turno corre server-side por Cloud Tasks; el admin recarga para ver el resultado). El stream real-time del **hilo** (las burbujas que el bot emite) vive en **conversations** (Firestore), no en bots.

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `bots:configurations` | listas y detalle de configuraciones, `/active` | crear/editar/borrar una configuración; crear/activar versión (cambia `current_version_*` denormalizado en la lista) |
| `bots:versions:{configurationId}` | lista + detalle de versiones de UN bot | crear versión, activar versión de ese bot |
| `bots:config-tools:{configurationId}` | set de tools (M:N) de UN bot | `setBotTools` de ese bot |
| `bots:tools` | listas y detalle del catálogo de tools, `/active` | crear/editar/borrar un tool |
| `bots:debug:{conversationId}` | state + events + tool-calls de UNA conversación | `resetState`, `dispatchManual` de esa conversación |

> **Tags por-recurso anidado** (`bots:versions:{id}`, `bots:config-tools:{id}`, `bots:debug:{cid}`): el historial de versiones de un bot es independiente del de otro; el set de tools de un bot es independiente; la depuración de una conversación es independiente. Taggear por id evita invalidar el cache de todos al mutar uno (mismo criterio que `crm:lead:{id}` / `conversations:thread:{id}`). **Cross-tag**: crear o activar una versión cruza **`bots:versions:{id}`** (la lista de versiones del bot) **y** `bots:configurations` (el `current_version_*` denormalizado en la fila de la tabla de configuraciones). `setBotTools` cruza `bots:config-tools:{id}` (y opcionalmente `bots:configurations` si el detalle embebe `tools`). Cada action revalida los tags que toca.

### `actions/bot-configuration.actions.ts`

El corazón del módulo: CRUD de configuraciones + sub-recursos de versiones (lista/crear/activar) + el M:N de tools por bot. Molde directo de `lead-status.actions.ts` de crm (catálogo admin) + el sub-recurso de versiones (molde de `DoctorAvailability` de staff). `/active` devuelve lista cruda.

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  botConfigurationCreateSchema,
  botConfigurationUpdateSchema,
} from "@/lib/schemas/bot-configuration.schema";
import { botVersionCreateSchema } from "@/lib/schemas/bot-configuration-version.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  BotConfigurationDetail,
  BotConfigurationItem,
  BotConfigurationOption,
  BotConfigurationVersionItem,
  BotToolOption,
  SetBotToolsRequest,
} from "@/types/bots.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const TAG = "bots:configurations";
const versionsTag = (id: string) => `bots:versions:${id}`;
const configToolsTag = (id: string) => `bots:config-tools:${id}`;

// ── Configuración (CRUD) ──

export async function listBotConfigurations(
  query: QueryRequest,
): Promise<ApiPaginated<BotConfigurationItem>> {
  return backendClient.post<ApiPaginated<BotConfigurationItem>>(
    ENDPOINTS.BOT_CONFIGURATIONS.LIST,
    query,
    { tags: [TAG] },
  );
}

export async function listActiveBotConfigurations(): Promise<BotConfigurationOption[]> {
  // `/active` devuelve lista CRUDA (sin envelope) — NO se lee `.data`.
  return backendClient.get<BotConfigurationOption[]>(ENDPOINTS.BOT_CONFIGURATIONS.ACTIVE, {
    tags: [TAG],
  });
}

export async function getBotConfiguration(id: string): Promise<ApiSingle<BotConfigurationDetail>> {
  return backendClient.get<ApiSingle<BotConfigurationDetail>>(
    ENDPOINTS.BOT_CONFIGURATIONS.GET(id),
    { tags: [TAG, versionsTag(id), configToolsTag(id)] },
  );
}

export async function createBotConfiguration(
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  const parsed = botConfigurationCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 BOT_CONFIGURATION_CODE_TAKEN (code duplicado) en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateBotConfiguration(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  const parsed = botConfigurationUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.UPDATE(id), // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteBotConfiguration(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.BOT_CONFIGURATIONS.DELETE(id)); // soft delete
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 si el bot está asignado a un canal/conversación viva (confirmar guard con backend).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Versiones (sub-recurso) ──

export async function listBotVersions(
  configurationId: string,
): Promise<ApiSingle<BotConfigurationVersionItem[]>> {
  // SingleResponse[list[...]] (no paginado; el front lee `.data` array — patrón crm activities).
  return backendClient.get<ApiSingle<BotConfigurationVersionItem[]>>(
    ENDPOINTS.BOT_CONFIGURATIONS.VERSIONS(configurationId),
    { tags: [versionsTag(configurationId)] },
  );
}

export async function getBotVersion(
  configurationId: string,
  versionId: string,
): Promise<ApiSingle<BotConfigurationVersionItem>> {
  return backendClient.get<ApiSingle<BotConfigurationVersionItem>>(
    ENDPOINTS.BOT_CONFIGURATIONS.VERSION_GET(configurationId, versionId),
    { tags: [versionsTag(configurationId)] },
  );
}

export async function createBotVersion(
  configurationId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationVersionItem>>> {
  const parsed = botVersionCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<BotConfigurationVersionItem>>(
      ENDPOINTS.BOT_CONFIGURATIONS.VERSIONS(configurationId),
      parsed.data,
    );
    revalidateTag(versionsTag(configurationId), "max");
    revalidateTag(TAG, "max"); // por si el current_version_* cambia / nueva versión visible en la fila
    return { ok: true, data };
  } catch (e) {
    // 400 EXTERNAL_WEBHOOK_URL_REQUIRED (provider=external_webhook sin URL) en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function activateBotVersion(
  configurationId: string,
  versionId: string,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.ACTIVATE_VERSION(configurationId, versionId),
      {},
    );
    // current_version_id = versionId. Cruza ambos tags (la fila de la tabla muestra "vN vigente").
    revalidateTag(versionsTag(configurationId), "max");
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 404 BOT_VERSION_NOT_FOUND / 400 BOT_VERSION_NOT_OWNED (la versión no es de este bot) en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Tools del bot (M:N) ──

export async function getBotConfigurationTools(
  configurationId: string,
): Promise<ApiSingle<BotToolOption[]>> {
  return backendClient.get<ApiSingle<BotToolOption[]>>(
    ENDPOINTS.BOT_CONFIGURATIONS.TOOLS(configurationId),
    { tags: [configToolsTag(configurationId)] },
  );
}

export async function setBotConfigurationTools(
  configurationId: string,
  input: SetBotToolsRequest,
): Promise<MutationResult<ApiSingle<BotToolOption[]>>> {
  try {
    const data = await backendClient.put<ApiSingle<BotToolOption[]>>(
      ENDPOINTS.BOT_CONFIGURATIONS.TOOLS(configurationId), // ← PUT bulk reemplaza el set
      input,
    );
    revalidateTag(configToolsTag(configurationId), "max");
    revalidateTag(TAG, "max"); // por si el detalle embebe tools
    return { ok: true, data };
  } catch (e) {
    // 404 BOT_TOOL_NOT_FOUND si algún tool_id no existe, en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/bot-tool.actions.ts`

Catálogo de tools (admin). Molde idéntico de `channel-account.actions.ts` de conversations. `/active` para el multiselect M:N.

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { botToolCreateSchema, botToolUpdateSchema } from "@/lib/schemas/bot-tool.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { BotToolDetail, BotToolItem, BotToolOption } from "@/types/bots.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const TAG = "bots:tools";

export async function listBotTools(query: QueryRequest): Promise<ApiPaginated<BotToolItem>> {
  return backendClient.post<ApiPaginated<BotToolItem>>(ENDPOINTS.BOT_TOOLS.LIST, query, {
    tags: [TAG],
  });
}

export async function listActiveBotTools(): Promise<BotToolOption[]> {
  // `/active` devuelve lista CRUDA — NO se lee `.data`. Alimenta el multiselect M:N.
  return backendClient.get<BotToolOption[]>(ENDPOINTS.BOT_TOOLS.ACTIVE, { tags: [TAG] });
}

export async function createBotTool(
  input: unknown,
): Promise<MutationResult<ApiSingle<BotToolDetail>>> {
  const parsed = botToolCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<BotToolDetail>>(
      ENDPOINTS.BOT_TOOLS.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 BOT_TOOL_CODE_TAKEN en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateBotTool(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotToolDetail>>> {
  const parsed = botToolUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<BotToolDetail>>(
      ENDPOINTS.BOT_TOOLS.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteBotTool(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.BOT_TOOLS.DELETE(id)); // soft delete
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 si el tool está asignado a algún bot (confirmar guard con backend).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/bot-debug.actions.ts`

Lectura de depuración (state/events/tool-calls de una conversación) + el reset del estado + el dispatch manual. Read-only salvo `resetState` (gated `BOT_STATE_WRITE`) y `dispatchManual` (gated `BOT_ENGINE_INVOKE`).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type {
  BotEventItem,
  BotToolCallItem,
  ConversationBotStateItem,
  DispatchManualRequest,
  ResetBotStateRequest,
} from "@/types/bots.types";
import type { MutationResult } from "./user.actions";

const debugTag = (cid: string) => `bots:debug:${cid}`;

// state puede ser null (la conversación existe pero el bot nunca corrió un turno) → el
// componente muestra el estado vacío, no error (patrón getLeadStatus → T | null de crm).
export async function getBotState(
  conversationId: string,
): Promise<ApiSingle<ConversationBotStateItem | null>> {
  return backendClient.get<ApiSingle<ConversationBotStateItem | null>>(
    ENDPOINTS.BOT_DEBUG.STATE(conversationId),
    { tags: [debugTag(conversationId)] },
  );
}

export async function listBotEvents(
  conversationId: string,
): Promise<ApiSingle<BotEventItem[]>> {
  // SingleResponse[list[...]] ordenado por turn_number (cronológico) — confirmar con backend.md.
  return backendClient.get<ApiSingle<BotEventItem[]>>(ENDPOINTS.BOT_DEBUG.EVENTS(conversationId), {
    tags: [debugTag(conversationId)],
  });
}

export async function listBotToolCalls(
  conversationId: string,
): Promise<ApiSingle<BotToolCallItem[]>> {
  return backendClient.get<ApiSingle<BotToolCallItem[]>>(
    ENDPOINTS.BOT_DEBUG.TOOL_CALLS(conversationId),
    { tags: [debugTag(conversationId)] },
  );
}

export async function resetBotState(
  conversationId: string,
  input: ResetBotStateRequest = {},
): Promise<MutationResult<ApiSingle<ConversationBotStateItem | null>>> {
  try {
    const data = await backendClient.post<ApiSingle<ConversationBotStateItem | null>>(
      ENDPOINTS.BOT_DEBUG.STATE_RESET(conversationId),
      input,
    );
    revalidateTag(debugTag(conversationId), "max");
    return { ok: true, data };
  } catch (e) {
    // 404 BOT_STATE_NOT_FOUND / 400 CONVERSATION_NOT_BOT (la conversación no atiende un bot) en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function dispatchBotTurnManual(
  input: DispatchManualRequest,
): Promise<MutationResult<null>> {
  try {
    await backendClient.post(ENDPOINTS.BOT_ENGINE.DISPATCH_MANUAL, input);
    // Tras el dispatch el state/events/tool-calls cambian → invalidar el tag de esa conversación.
    revalidateTag(debugTag(input.conversation_id), "max");
    return { ok: true };
  } catch (e) {
    // 400 CONVERSATION_NOT_BOT / 400 NO_CURRENT_VERSION (el bot no tiene versión vigente) en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **`dispatchBotTurnManual` es debugging del admin, NO el flujo normal** (spec §6): el turno productivo lo dispara Cloud Tasks → `POST /engine/dispatch` (OIDC, sin RBAC, server-to-server). El front solo expone `dispatch-manual` (gated `BOT_ENGINE_INVOKE`) para re-correr un turno al diagnosticar. El backend puede encolarlo o correrlo síncrono — el front no asume nada del timing; tras el retorno, recarga el estado/eventos del panel de depuración (el resultado puede tardar si es asíncrono → mostrar un hint "El turno puede tardar unos segundos; usa Actualizar para ver el resultado").

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/bots/configuraciones/page.tsx`

Molde directo de `crm/estados-lead/page.tsx` / `catalog` Verticals: RSC con `requirePermission` + prefetch de la primera página. CRUD + sub-recursos (versiones/tools) en el drawer/tabs de la fila seleccionada. `defaultSort` sobre columna real (`created_on desc` — spec §6).

```tsx
import { listBotConfigurations } from "@/actions/bot-configuration.actions";
import { requirePermission } from "@/lib/auth/session";

import { BotConfigurationsClient } from "./_components/BotConfigurationsClient";

export const metadata = { title: "Configuraciones de bots" };

export default async function BotConfigurationsPage() {
  await requirePermission("BOT_CONFIGURATIONS_READ");
  const initialData = await listBotConfigurations({
    pagination: { skip: 0, limit: 50 }, // catálogo chico; una página suele bastar
    sorting: { sort_by: "created_on", sort_order: "desc" }, // columna real; coincide con el client
    filters: null,
  });
  return <BotConfigurationsClient initialData={initialData} />;
}
```

### `app/(main)/bots/tools/page.tsx`

Catálogo de tools (admin). Idéntico molde. `defaultSort` sobre columna real (`created_on desc` o `code`/`name` si están whitelistadas — confirmar `ALLOWED_FIELDS` con backend).

```tsx
import { listBotTools } from "@/actions/bot-tool.actions";
import { requirePermission } from "@/lib/auth/session";

import { BotToolsClient } from "./_components/BotToolsClient";

export const metadata = { title: "Herramientas de bots" };

export default async function BotToolsPage() {
  await requirePermission("BOT_TOOLS_READ");
  const initialData = await listBotTools({
    pagination: { skip: 0, limit: 50 },
    sorting: { sort_by: "created_on", sort_order: "desc" }, // columna real; coincide con el client
    filters: null,
  });
  return <BotToolsClient initialData={initialData} />;
}
```

### `app/(main)/bots/depuracion/page.tsx`

Panel de depuración por conversación. Toma la conversación por **deep-link `?c=<conversationId>`** (se entra desde el inbox de conversations o la config del bot). Si hay `?c=`, prefetcha state + events + tool-calls; si no, muestra un estado vacío "Selecciona una conversación para depurar" + un campo para pegar/buscar un `conversation_id`.

```tsx
import { getBotState, listBotEvents, listBotToolCalls } from "@/actions/bot-debug.actions";
import { requirePermission } from "@/lib/auth/session";

import { BotDebugShell } from "./_components/BotDebugShell";

export const metadata = { title: "Depuración de bots" };

interface PageProps {
  searchParams: Promise<{ c?: string }>; // conversación a depurar (deep-link)
}

export default async function BotDebugPage({ searchParams }: PageProps) {
  await requirePermission("BOT_STATE_READ");
  const { c } = await searchParams;

  if (!c) {
    // Sin conversación seleccionada: el shell muestra el estado vacío + input de conversation_id.
    return <BotDebugShell initialConversationId={null} initialState={null} initialEvents={[]} initialToolCalls={[]} />;
  }

  // Prefetch en paralelo (sin waterfall). state puede venir null (bot nunca corrió un turno).
  const [stateRes, eventsRes, toolCallsRes] = await Promise.all([
    getBotState(c),
    listBotEvents(c),
    listBotToolCalls(c),
  ]);

  return (
    <BotDebugShell
      initialConversationId={c}
      initialState={stateRes.data}
      initialEvents={eventsRes.data}
      initialToolCalls={toolCallsRes.data}
    />
  );
}
```

> **`?c=` hace al panel deep-linkable**: abrir `/bots/depuracion?c=abc123` carga el estado/eventos/tool-calls de esa conversación. El `BotDebugShell` lo sincroniza con `nuqs` (`useQueryState("c")`) — cambiar de conversación (o pegar otro id) actualiza la URL sin recargar, y la URL sobrevive refresh/compartir. El link "Ver actividad del bot" del hilo de conversations apunta a `/bots/depuracion?c=<conversation_id>`.

## Client components — esqueletos

> **No reproduzco los archivos completos** — los CRUD siguen `crm/estados-lead` + `admin/users/UserDrawer`; el editor de versiones (system_prompt + JSON) y el panel de depuración (timeline) son las piezas sustancialmente nuevas y se detallan aparte. La UI detallada (mockups, copy) vive en [`ui.md`](./ui.md).

### `BotConfigurationsClient.tsx`

Molde de `LeadStatusesClient.tsx` (crm) / `ChannelAccountsClient.tsx` (conversations): tabla + drawer CRUD + sub-recursos.

- `useTableQuery`: `queryKey: "bots:configurations"`, `fetcher: listBotConfigurations`, `defaultSort: { field: "created_on", order: "desc" }` (**columna real**, coincide con el prefetch RSC), `searchFields: ["name", "code"]` (**client-side** si no están whitelistadas; busca sobre la página visible), `initialData`.
- Columns: `actions`, `name` (Nombre), `code` (Código, monoespaciado), `bot_type` (badge con `BOT_TYPE_META` — label ES + color), `current_version_number` (Badge "v3 vigente" o "Sin versión" gris si `current_version_id == null` → el bot **NO** es usable, anotarlo visualmente), `max_turns_per_conversation` ("Sin límite" si null), `active` (Badge "Activo"/"Inactivo"). **Ninguna columna denormalizada/derivada es `isSortable`** salvo lo whitelistado (`code`/`name`/`bot_type`/`created_on` — spec §6).
- **RowActions**: Editar (gated `BOT_CONFIGURATIONS_UPDATE`) → `BotConfigurationDrawer`; **Versiones** (gated `BOT_CONFIGURATION_VERSIONS_READ`) → abre el `BotVersionsPanel`; **Herramientas** (gated `BOT_CONFIGURATIONS_READ` para ver / `BOT_CONFIGURATIONS_UPDATE` para editar el M:N — confirmar con backend) → abre `BotToolsAssignment`; Eliminar (gated `BOT_CONFIGURATIONS_DELETE`, danger). El delete es soft; `ConfirmDialog`: "Se eliminará el bot. Las conversaciones que atendía dejarán de tener bot asignado."
- Botón "Nuevo bot" gated `BOT_CONFIGURATIONS_CREATE` → abre `BotConfigurationDrawer`.

> **El badge "Sin versión" es importante**: un bot sin `current_version_id` **no es usable** (el dispatch da `NO_CURRENT_VERSION` 400 — spec §7). La tabla lo marca con un badge ámbar "Sin versión vigente" + un hint en el drawer/panel de versiones ("Crea y activa una versión para que el bot pueda atender."). Esto guía al admin al flujo correcto (crear config → crear versión → activar).

### `BotConfigurationDrawer.tsx`

Drawer create/edit. Molde de `LeadStatusDrawer` (crm). `useForm` con `botConfigurationCreateSchema`/`botConfigurationUpdateSchema`. Campos:

- **`code`** (Input — slug; solo en create, disabled en edit; hint "Identificador único, ej. `preventa_dental`").
- **`name`** (Input — "Bot de preventa").
- **`bot_type`** (Dropdown — `BOT_TYPES`: Preventa/Postventa/General/Personalizado).
- **`description`** (Textarea — opcional).
- **`max_turns_per_conversation`** (Input number — opcional; hint "Límite de turnos del bot por conversación. Vacío = sin límite."). Guard opcional (spec §0.9).
- **`active`** (Switch — solo en edit).
- **Errores de servidor**: `409 BOT_CONFIGURATION_CODE_TAKEN` → `MessageBar intent="error"` sin cerrar el drawer.
- En `onSuccess`: cerrar el drawer + `router.refresh()` (la tabla se re-pinta vía el tag invalidado). En **create**, opcionalmente abrir el `BotVersionsPanel` del bot recién creado (guiar a "ahora crea su primera versión").

> **El drawer NO captura API keys ni credenciales de provider** (spec §0.5): las credenciales (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) son **globales por entorno** (env del backend vía `--set-secrets` de Cloud Run), NO per-bot. El provider/model se elige por **versión** (en el `BotVersionEditor`), no en la config del bot. No hay ningún campo de secreto en este módulo (a diferencia del `secret_name` per-canal de conversations).

### `BotVersionsPanel.tsx` (tab/sección de versiones)

Panel de versiones de un bot (se abre desde la RowAction "Versiones" o como tab del drawer de la config). Molde del sub-recurso de `DoctorAvailability` (staff) — lista del sub-recurso + crear + acción por fila.

- **Lista de versiones** (`listBotVersions(configurationId)` → `BotConfigurationVersionItem[]`, orden por `version desc`): cada fila muestra `version` (#3), `provider` (`BOT_PROVIDER_META.label`) + `model_name`, `is_current` (badge "Vigente" verde si `is_current`), `is_active` (badge "Inactiva" gris si `!is_active`), `created_on` (fecha local), `notes` (changelog, truncado). La versión vigente se resalta.
- **Botón "Nueva versión"** (gated `BOT_CONFIGURATION_VERSIONS_WRITE`) → abre el `BotVersionEditor` (create). Opcional: "Duplicar como nueva versión" pre-popula el editor con el `system_prompt`/`provider`/`model_name`/`parameters` de una versión existente (editar prompt = nueva versión, NO in-place — spec §2).
- **Acción "Activar"** por fila (gated `BOT_CONFIGURATION_VERSIONS_WRITE`; visible si `!is_current`) → `ConfirmDialog`: "¿Activar la versión {n}? El bot empezará a usar este prompt en los próximos turnos." → `activateBotVersion(configurationId, versionId)` → `setVersions(...)` local + `router.refresh()` (la fila pasa a "Vigente"; la tabla de configuraciones muestra "v{n} vigente"). Errores: `BOT_VERSION_NOT_OWNED` (400) / `BOT_VERSION_NOT_FOUND` (404) en `MessageBar`.
- **Ver versión** (gated `BOT_CONFIGURATION_VERSIONS_READ`) → abre el `BotVersionEditor` en modo **read-only** (las versiones son inmutables — no se editan in-place; el system_prompt/params se muestran sin editar, con un botón "Duplicar como nueva versión").

> **Las versiones son inmutables** (spec §2): NO se editan in-place. "Editar el prompt" = crear una versión nueva (`max+1`) y activarla. El `BotVersionsPanel` no tiene "Editar versión" — tiene "Nueva versión" (puede partir de una existente como base) + "Activar". Esto da un **historial/changelog** del prompt (cada versión es un snapshot con `notes`). El `is_active` (soft-disable) es distinto del `is_current` (vigente): una versión inactiva no se puede activar (confirmar el guard con backend).

### `BotVersionEditor.tsx` (editor de versión — pieza nueva)

Editor de una versión nueva (o vista read-only de una existente). Es **la pieza de más densidad de contenido del módulo de configuración**: un `system_prompt` largo + selects de provider/model + un JSON editor de `parameters`. `useForm` con `botVersionCreateSchema`. Campos:

- **`system_prompt`** (Textarea grande, monoespaciado, ~12-20 filas, redimensionable; hint "Las instrucciones del bot. Define su personalidad, qué puede hacer y cuándo escalar a un humano."). Es el corazón del bot.
- **`provider`** (Dropdown — `BOT_PROVIDERS` con `BOT_PROVIDER_META`): **openai/claude habilitados**; `vertex_ai`/`azure_openai`/`external_webhook` deshabilitados con "(no disponible aún)" (spec §0.2). Default `openai`.
- **`model_name`** (Combobox editable — `PROVIDER_MODEL_PRESETS[provider]` como sugerencias + texto libre; default **`gpt-4.1-mini`** si provider=openai). Al cambiar de provider, sugiere el primer preset del nuevo provider. Hint "Modelo del proveedor; el default es gpt-4.1-mini."
- **`parameters`** (JSON editor — textarea monoespaciado con parse/validate; ver [Editor de JSON](#editor-de-json-parameters_schema--parameters)). Placeholder con ejemplo `{ "temperature": 0.7, "max_tokens": 1024 }`. Hint "Parámetros del modelo (temperature, max_tokens, top_p…). Depende del proveedor."
- **`external_webhook_url`** / **`external_webhook_secret_name`** (Inputs — **solo visibles si `provider === "external_webhook"`**, que está deshabilitado en el MVP; quedan en el form para cuando F4 cablee el engine externo). El `superRefine` del Zod exige la URL si el provider es externo (`EXTERNAL_WEBHOOK_URL_REQUIRED`).
- **`notes`** (Input/Textarea — changelog opcional de esta versión: "Ajuste del tono", "Agregada tool set_lead_status").
- **Submit** (create): `createBotVersion(configurationId, ...)` → `MessageBar` de éxito + opción "Activar ahora" (encadena `activateBotVersion`) → cerrar.
- **Read-only** (ver versión existente): todos los campos disabled + botón "Duplicar como nueva versión" (clona los valores a un nuevo editor en modo create).

> **El JSON editor de `parameters` es un textarea con validación, NO un editor de código** (mismo criterio para `parameters_schema` del tool): un `<textarea>` Fluent monoespaciado + parse `JSON.parse` on-blur/on-submit. Si el JSON es inválido → error inline en español ("Los parámetros no son JSON válido"). El Zod (`jsonObjectString`) lo valida también en el server (defensa). Un editor de código real (Monaco/CodeMirror con syntax highlight + autocompletado) es una **mejora futura** (anotada en TODOs) — agrega peso de bundle y no es crítico para el MVP. Documentar el helper (`JsonField.tsx`) si se extrae.

### `BotToolsAssignment.tsx` (editor M:N de tools del bot — molde StatusMatrixEditor)

Editor de las tools que un bot puede usar (M:N `bot_configuration_tool`). **Molde directo del `StatusMatrixEditor` de crm** (multiselect que reemplaza el set completo) + el `SearchableOptionList` (mismo helper que roles/permisos en `UserDrawer` — cero código nuevo).

- Recibe `configurationId`. Carga `getBotConfigurationTools(configurationId)` → preselecciona los `tool_id` actuales, y `listActiveBotTools()` → todas las tools del catálogo (opciones).
- Renderiza un **multiselect** (`SearchableOptionList`) con todas las tools activas; cada opción muestra `name` + `code` (monoespaciado) + un badge si `requires_confirmation`. Al guardar → `setBotConfigurationTools(configurationId, { tool_ids })` (reemplaza el set completo). Gated `BOT_CONFIGURATIONS_UPDATE` (o el permiso que el backend exija para el M:N — confirmar).
- Estado vacío del catálogo: "No hay herramientas en el catálogo. Crea herramientas en la sección Herramientas." (link a `/bots/tools`).

> **El M:N reemplaza el set completo** (bulk PUT `{tool_ids:[]}`, spec §6): igual que la matriz de transiciones de crm — no es add/remove incremental, es "estas son las tools del bot ahora". El front manda el array completo de `tool_id` seleccionados. Las tools `DIFERIDAS` (`book_appointment`/`check_availability`/`cancel_appointment` → scheduling) **NO** aparecen en el catálogo (no se seedean — spec §0.4), así que no son seleccionables hasta que scheduling #7 las registre.

### `BotToolsClient.tsx`

Molde de `ChannelAccountsClient.tsx` (conversations) / `LeadStatusesClient.tsx` (crm): tabla + drawer CRUD del catálogo de tools.

- `useTableQuery`: `queryKey: "bots:tools"`, `fetcher: listBotTools`, `defaultSort: { field: "created_on", order: "desc" }` (**columna real**), `searchFields: ["name", "code", "target_service"]` (**client-side**), `initialData`.
- Columns: `actions`, `name` (Nombre), `code` (Código, monoespaciado), `target_service` (monoespaciado — "crm.person_lead_status.transition"), `requires_confirmation` (Badge "Requiere confirmación" si true), `is_active` (Badge "Activa"/"Inactiva"), `active`. `description` no es columna (es larga; va en el drawer/tooltip).
- **RowActions**: Editar (gated `BOT_TOOLS_WRITE`) → `BotToolDrawer`; Eliminar (gated `BOT_TOOLS_WRITE`, danger). `ConfirmDialog`: "Se eliminará la herramienta. Los bots que la usaban dejarán de tenerla."
- Botón "Nueva herramienta" gated `BOT_TOOLS_WRITE` → abre `BotToolDrawer`.

> **`BOT_TOOLS_{READ,WRITE}` (no CRUD de 4)** (spec §5): el catálogo de tools usa `BOT_TOOLS_READ` (ver) + `BOT_TOOLS_WRITE` (crear/editar/borrar) — NO los 4 permisos `_CREATE/_UPDATE/_DELETE` separados que tiene `BOT_CONFIGURATIONS_*`. El front gatea crear/editar/borrar con el único `BOT_TOOLS_WRITE`. Idem versiones (`BOT_CONFIGURATION_VERSIONS_{READ,WRITE}`) y state (`BOT_STATE_{READ,WRITE}`).

### `BotToolDrawer.tsx`

Drawer create/edit del tool. `useForm` con `botToolCreateSchema`/`botToolUpdateSchema`. Campos:

- **`code`** (Input — slug; solo en create, disabled en edit; "list_verticals", "set_lead_status").
- **`name`** (Input — "Listar verticales").
- **`description`** (Textarea — obligatoria; hint "La usa el modelo para decidir cuándo invocar la herramienta. Sé descriptivo."). Es semánticamente importante (el LLM la lee).
- **`target_service`** (Input monoespaciado — "modulo.servicio.funcion", ej. "crm.person_lead_status.transition"; hint "Función del backend que ejecuta la herramienta. Si no está registrada, fallará en tiempo de ejecución."). El front valida el formato `modulo.servicio.funcion`; NO valida contra el `TOOL_REGISTRY` (eso es runtime: `TOOL_NOT_REGISTERED` 404).
- **`parameters_schema`** (JSON editor — JSON Schema; mismo `JsonField` que el editor de versiones; placeholder con un ejemplo de JSON Schema `{ "type": "object", "properties": { ... }, "required": [...] }`).
- **`requires_confirmation`** (Switch — "Requiere confirmación antes de ejecutarse").
- **`is_active`** (Switch — "Activa").
- **`active`** (Switch — solo en edit; ActiveMixin).
- **Errores de servidor**: `409 BOT_TOOL_CODE_TAKEN` → `MessageBar` sin cerrar el drawer.
- En `onSuccess`: cerrar el drawer + `router.refresh()`.

### `BotDebugShell.tsx` (panel de depuración — pieza nueva, molde timeline crm/conversations)

> **Honestidad (igual que pide la spec)**: este panel (estado del bot + timeline de turnos + tool-calls, todo read-only) es **bespoke** dentro de Fluent UI 9 — se ejecuta DENTRO de Fluent (tokens, primitivas propias, JSON viewers simples). Es **el componente más rico del módulo** (como el `ActivityTimeline` lo es de crm). Es **read-only** salvo el "Reiniciar estado" (gated `BOT_STATE_WRITE`) y el "Disparar turno" (gated `BOT_ENGINE_INVOKE`). NO hay tiempo real ni polling — carga a demanda + botón "Actualizar".

Props: `{ initialConversationId: string | null; initialState: ConversationBotStateItem | null; initialEvents: BotEventItem[]; initialToolCalls: BotToolCallItem[] }`.

**Layout**: una columna (o 2 columnas en desktop ancho): arriba `BotStateCard` (resumen del estado actual del bot en la conversación), debajo el `BotEventTimeline` (turnos) intercalado con `BotToolCallList` (las tool-calls de cada turno, o una sección aparte). Header con el `conversation_id` (monoespaciado, con botón "Copiar") + un link "Ver conversación" → `/conversaciones/bandeja?c=<cid>` (gated `CONVERSATIONS_READ`) + botón "Actualizar" (refetch) + (si `BOT_ENGINE_INVOKE`) botón "Disparar turno" (`dispatch-manual`).

**Estado central** (molde del `ActivityTimeline` de crm, pero a demanda — sin polling):

```ts
// Conversación a depurar, sincronizada con la URL (?c=) vía nuqs. Deep-linkable.
const [conversationId, setConversationId] = useQueryState("c", {
  defaultValue: initialConversationId ?? "",
});
const [state, setState] = useState<ConversationBotStateItem | null>(initialState);
const [events, setEvents] = useState<BotEventItem[]>(initialEvents);
const [toolCalls, setToolCalls] = useState<BotToolCallItem[]>(initialToolCalls);
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
// Token monotónico: al cambiar de conversación rápido, una respuesta vieja no pisa la nueva
// (idéntico a OfficeClosuresTab / ActivityTimeline de crm).
const reqIdRef = useRef(0);

// Carga (a demanda) de state + events + tool-calls. Reutilizable por "Actualizar" / tras dispatch.
const loadDebug = useCallback((cid: string, silent = false) => {
  if (!cid) return;
  const reqId = ++reqIdRef.current;
  if (!silent) setLoading(true);
  setError(null);
  void Promise.all([getBotState(cid), listBotEvents(cid), listBotToolCalls(cid)])
    .then(([s, e, t]) => {
      if (reqId !== reqIdRef.current) return; // respuesta superada → descartar
      setState(s.data);
      setEvents(e.data);
      setToolCalls(t.data);
      setLoading(false);
    })
    .catch(() => {
      if (reqId !== reqIdRef.current) return;
      setError("No se pudo cargar la depuración del bot. Intenta de nuevo.");
      setLoading(false);
    });
}, []);

// Al cambiar de conversación (deep-link / input), recargar. El initial viene del RSC.
useEffect(() => {
  if (conversationId && conversationId !== initialConversationId) loadDebug(conversationId);
}, [conversationId, initialConversationId, loadDebug]);
```

- **Estado vacío** (sin `?c=`): "Selecciona una conversación para depurar" + un `Input` para pegar/buscar un `conversation_id` (o un link "Entra desde el inbox de conversaciones").
- **Estado del bot null** (la conversación existe pero el bot nunca corrió un turno): `BotStateCard` muestra "El bot aún no ha actuado en esta conversación." (no error — `getBotState` devuelve `null`, patrón crm `getLeadStatus`).
- **"Reiniciar estado"** (gated `BOT_STATE_WRITE`; visible si `state != null`): `ConfirmDialog` ("¿Reiniciar el estado del bot? Se borrarán los slots e intención acumulados; el bot empezará de cero en el próximo turno.") → `resetBotState(cid)` → `setState(result.data)` + recargar. Errores `BOT_STATE_NOT_FOUND`/`CONVERSATION_NOT_BOT` en `MessageBar`.
- **"Disparar turno"** (gated `BOT_ENGINE_INVOKE`): `dispatchBotTurnManual({ conversation_id: cid })` → hint "El turno puede tardar; usa Actualizar para ver el resultado." → tras unos segundos, "Actualizar" recarga el timeline con el nuevo turno. Errores `CONVERSATION_NOT_BOT`/`NO_CURRENT_VERSION` en `MessageBar`.

### `BotStateCard.tsx`

Tarjeta del estado actual del bot en la conversación (read-only). Muestra:

- `current_intent` (texto o "—"), `turn_count` (badge "5 turnos"), `last_bot_turn_at` (fecha/hora local relativa — **client-only**), `last_node` (texto o "—").
- `bot_configuration_id` → resuelto a `code`/`name` si el shell lo tiene (o link a la config); `bot_configuration_version_id` → "versión con la que arrancó" (badge "v2").
- `collected_slots` (JSON viewer read-only — `<pre>` monoespaciado con `JSON.stringify(slots, null, 2)`, o una tabla key→value si el schema es plano). Vacío `{}` → "Sin datos recolectados".

### `BotEventTimeline.tsx` (timeline de turnos)

Timeline de los `BotEvent` de la conversación (read-only). Molde del `ActivityTimeline` de crm: agrupación por día **client-only** (lección TZ), filas memoizadas, sin polling.

```ts
// Agrupación por día computada en cliente (BotDebugShell es "use client") con la TZ del navegador.
// new Date() que afecta render = client-only (SSR en UTC desfasa el día en TZ Lima -05:00).
const dayGroups = useMemo(() => {
  const sorted = [...events].sort(
    (a, b) => new Date(a.created_on).getTime() - new Date(b.created_on).getTime(), // cronológico
  );
  return groupByDay(sorted, (e) => e.created_on); // [{ label: "Hoy"|"Ayer"|"12 may", items: [...] }]
}, [events]);
```

- Cada `BotEventRow` (memoizada) muestra: ícono + label del `event_type` (`BOT_EVENT_TYPE_META`), `turn_number` (#3), hora local (**client-only**), y según el tipo: `tokens_in`/`tokens_out` (badge "1.2k tok"), `latency_ms` ("840 ms"), `cost_estimated_usd` (formateado "$0.000142"), `error` (texto rojo si `turn_failed`), `input_message_id`/`output_message_id` (referencia opaca al hilo — ver nota). Las tool-calls de ese turno (`toolCalls.filter(tc => tc.bot_event_id === event.id)`) se anidan o se enlazan.
- Estado vacío: "El bot aún no ha tenido turnos en esta conversación."

> **`BotEventRow` memoizada + agrupación client-only** (regla vercel-react + lección TZ): el timeline puede tener decenas de turnos; `React.memo` evita re-render de los que no cambiaron. La agrupación "Hoy"/"Ayer"/fecha usa `new Date()` (hoy del navegador) → **client-only**, NUNCA en SSR (SSR en UTC desfasa el día en TZ negativas como Lima `-05:00`). La hora de cada turno se formatea en **local** con `lib/utils/date.ts`, nunca `toISOString()`.

> **`input_message_id`/`output_message_id` en la fila** (spec §0.3): son el `mid` (doc-id Firestore), NO un mensaje resoluble en bots. La fila los muestra como referencia truncada ("Entrada: `wamid.HBg…`", "Salida: `8f2a…`") con un tooltip del id completo. Un link al hilo de conversations (`/conversaciones/bandeja?c=<conversation_id>`) lleva al mensaje en su contexto (gated `CONVERSATIONS_READ`) — el bot no embebe el contenido del mensaje (vive en Firestore, dominio de conversations).

### `BotToolCallList.tsx` (tool-calls — read-only, JSON viewer)

Lista de las `BotToolCall` de la conversación (o de un turno). Read-only. Cada `BotToolCall`:

- `bot_tool_code` (monoespaciado — "set_lead_status"; si null, el `bot_tool_id`), `status` (badge con `TOOL_CALL_STATUS_META` — ícono + label ES + color), `latency_ms` ("120 ms"), `started_at`/`completed_at` (hora local **client-only**).
- `arguments` (JSON viewer — `<pre>` con `JSON.stringify(arguments, null, 2)`).
- `result` (JSON viewer — si `status==='success'`; si `status==='error'/'timeout'`, mostrar `error_message` en rojo).
- `tool_use_id` (referencia opaca; tooltip).
- Estado vacío: "El bot no ha invocado herramientas en esta conversación."

> **JSON viewers read-only** (`collected_slots`, `arguments`, `result`, `metadata`): un `<pre>` monoespaciado con `JSON.stringify(value, null, 2)` dentro de un contenedor scrolleable con borde Fluent — NO un editor (es solo lectura). Para objetos grandes, un acordeón colapsable ("Ver argumentos" / "Ver resultado") evita inflar la fila. No se introduce una librería de JSON tree-viewer en el MVP (mejora futura).

## Editor de JSON (`parameters_schema` / `parameters`)

> Pieza transversal: tanto el `parameters` de la versión como el `parameters_schema` del tool se capturan como **JSON crudo en un textarea** y se validan en cliente como JSON parseable a objeto (el Zod `jsonObjectString` los `transform`a a `Record<string, unknown>` antes de enviarlos). Patrón único reusable (`JsonField.tsx` local o inline).

- **Captura**: `<textarea>` Fluent monoespaciado (`fontFamily: tokens.fontFamilyMonospace`), redimensionable, ~8-12 filas, con placeholder de ejemplo.
- **Pre-populado** (al editar/duplicar): `JSON.stringify(value, null, 2)` (pretty-printed, 2 espacios).
- **Validación**: on-blur + on-submit, `JSON.parse`. Inválido → error inline en español ("No es JSON válido" / "Debe ser un objeto JSON"). El Zod re-valida en el server (defensa en profundidad).
- **Botón "Formatear"** (opcional): re-pretty-printa el JSON válido (`JSON.stringify(JSON.parse(raw), null, 2)`).
- **NO** se introduce Monaco/CodeMirror (peso de bundle; mejora futura anotada en TODOs). El textarea + parse alcanza para el MVP.

## Reglas de performance (vercel-react-best-practices)

| Regla | Aplicación en bots |
|---|---|
| **Evitar waterfalls de datos** | El RSC de `depuracion` hace `Promise.all([getBotState, listBotEvents, listBotToolCalls])` (paralelo). El `BotVersionsPanel`/`BotToolsAssignment` cargan su sub-recurso al abrirse (no se prefetchan todos en la tabla). |
| **Memoizar lo que se re-renderiza** | `BotEventRow` (timeline) y las filas de tool-calls son `React.memo`. El estado indexado/ordenado conserva referencias → solo lo que cambió se re-renderiza. `onSelect`/callbacks son `useCallback` estables. |
| **Defer reads (cargar a demanda)** | El panel de depuración NO se prefetcha para todas las conversaciones — solo la deep-linkeada (`?c=`). Las versiones/tools de un bot se cargan al abrir su panel, no en la tabla. |
| **Sin polling ni tiempo real** | bots NO pollea ni abre listeners (a diferencia de conversations). La depuración carga a demanda + "Actualizar" manual. Esto ahorra requests y complejidad — el turno corre server-side por Cloud Tasks; el admin recarga para ver el resultado. |
| **`useTableQuery` con `defaultPageSize` = `limit` del prefetch** | El RSC prefetcha `limit: 50` (configuraciones/tools) → el `useTableQuery` usa `defaultPageSize: 50` (lección desync footer de crm: si difieren, el footer desincroniza + flash). |
| **No definir componentes inline** | `BotEventRow`/`BotToolCallList`/etc. se definen a nivel de módulo (no dentro del render del padre) — sino se re-crean en cada render y rompen la memoización. |
| **`useTransition` para acciones lentas** | Activar versión / dispatch-manual con `startTransition` → no congela la UI; el botón muestra `isPending`. |

## Lección TZ (recap)

> Cualquier reloj/`now` del cliente que afecte el render = **client-only** (lección TZ recurrente de staff/crm/conversations; SSR en UTC desfasa el día en TZ negativas como Lima `-05:00`).

- **Separadores "Hoy"/"Ayer"/fecha del timeline de turnos** (`BotEventTimeline`): `new Date()` (hoy del navegador), computado en `"use client"`, NUNCA en SSR.
- **Hora local de cada turno / tool-call** (`created_on`, `started_at`, `completed_at`, `last_bot_turn_at` → "14:32"): formatear en **local** del navegador, NUNCA con `toISOString()` (que muestra UTC). Usar `lib/utils/date.ts` (`formatTime`/`formatDate`/relativa).
- **Hora relativa de `last_bot_turn_at`** ("hace 5 min" en `BotStateCard`): client-only; para evitar mismatch de hidratación, `useState(null) + useEffect` (render absoluto/placeholder en SSR, relativo tras montar).
- **El editor de versiones/tools NO compone fechas** — los timestamps los pone el backend. No hay `datetime-local` en este módulo.

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| 3 rutas hermanas (`configuraciones`/`tools`/`depuracion`), sin `layout.tsx` | Mismo criterio que catalog/clinic/staff/crm/conversations; el `(main)/layout.tsx` ya envuelve con `MainShell`. Versiones/tools viven en el drawer/tabs de la config; la depuración en `?c=`. |
| Conversación a depurar en `?c=` (URL state, nuqs) — NO sub-ruta | Deep-linkable (`/bots/depuracion?c=abc`); el link "Ver actividad del bot" del hilo de conversations apunta acá; sobrevive refresh. Mismo criterio que `?tab=`/`?c=` de crm/conversations. |
| **Sin tiempo real ni polling en bots** | A diferencia de conversations (Firestore listener + polling de la lista), bots es CRUD de config + lectura de depuración a demanda. El turno corre server-side (Cloud Tasks); el admin recarga ("Actualizar") para ver el resultado. El stream del hilo (burbujas del bot) vive en conversations (Firestore), no en bots. |
| Versiones inmutables: "editar prompt" = nueva versión + activar | Spec §2: el system_prompt/params no se editan in-place. Da un historial/changelog (cada versión = snapshot con `notes`). El panel tiene "Nueva versión" (puede partir de una existente) + "Activar", NO "Editar versión". |
| `current_version_id == null` → bot NO usable (badge ámbar) | Spec §7 (`NO_CURRENT_VERSION` 400 en dispatch/activate). La tabla marca "Sin versión vigente"; el flujo guía a crear config → versión → activar. |
| Provider/model por **versión**, no por config | El motor lo elige `BotConfigurationVersion.provider/model_name` (spec §2). El select de provider habilita solo openai/claude (MVP); el resto deshabilitado "(no disponible aún)". Default `gpt-4.1-mini`. |
| **`external_webhook` diseñado pero deshabilitado en la UI** | Spec §0.2: las entidades llevan los campos (`external_webhook_url/secret_name`) pero el engine externo está DIFERIDO. El select lo muestra deshabilitado; los campos solo si se elige ese provider (que no se puede en el MVP). El schema los valida para cuando F4 los cablee (aditivo). |
| **NO se capturan API keys/credenciales en el front** | Spec §0.5: `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` son globales por entorno (env del backend). No hay campo de secreto en ningún drawer (a diferencia del `secret_name` per-canal de conversations). |
| `parameters`/`parameters_schema` = textarea JSON + parse/validate, no editor de código | Un `<textarea>` monoespaciado + `JSON.parse` (Zod `jsonObjectString` `transform`a a objeto) alcanza para el MVP. Monaco/CodeMirror = mejora futura (peso de bundle). |
| El front NO valida que `parameters_schema` sea JSON Schema válido | Solo JSON parseable a objeto; el dialecto JSON Schema (ajv) es mejora futura. El adapter/LLM rechaza un schema malformado en runtime. |
| `target_service` NO se valida contra el registry en el front | El front valida el formato `modulo.servicio.funcion`; la existencia en `TOOL_REGISTRY` es runtime (`TOOL_NOT_REGISTERED` 404). |
| M:N de tools = bulk PUT que reemplaza el set | Molde `StatusMatrixEditor` de crm; no add/remove incremental. Las tools DIFERIDAS (scheduling) no aparecen en el catálogo hasta #7. |
| `input_message_id`/`output_message_id` = `string \| null` opacos | Spec §0.3: el `mid` (doc-id Firestore), NO FK→message (no existe). Referencia al hilo de conversations; link cruzado opcional. |
| `cost_estimated_usd` = `string` (numeric) | `numeric(10,6)` → string para no perder precisión; el front lo formatea con `Number()` solo para mostrar. |
| `getBotState` → `T \| null` (estado vacío, no error) | El backend responde `SingleResponse[null]` cuando la conversación existe pero el bot nunca corrió un turno — `BotStateCard` muestra "El bot aún no ha actuado". Patrón `getLeadStatus` de crm. |
| **`defaultSort`/`isSortable`/`searchFields` SOLO columnas reales de `ALLOWED_FIELDS`** | **Lección hotfix `cd10c78` de staff**: ordenar/filtrar server-side por un derivado (`current_version_number`, `bot_type` label) no whitelistado devuelve 400. `defaultSort` configuraciones/tools = `created_on desc` (columna real); el `defaultSort` del client DEBE coincidir con el prefetch RSC. Búsqueda por name/code = client-side. |
| Permisos `_{READ,WRITE}` (no 4 CRUD) salvo configuraciones | Spec §5: tools/versions/state usan `_{READ,WRITE}`; solo `BOT_CONFIGURATIONS_*` tiene los 4 (`_CREATE/_UPDATE/_DELETE`). El front gatea acorde. |
| ASESOR = read-only (config + depuración; sin tools) | Spec §5: ADMIN todo; ASESOR `BOT_CONFIGURATIONS_READ` + `BOT_STATE_READ` + `BOT_EVENTS_READ` + `BOT_TOOL_CALLS_READ` (ve Configuraciones + Depuración, NO Herramientas); DOCTOR ninguno. |
| `/engine/dispatch` (OIDC) NO en el front; solo `dispatch-manual` | Spec §6: el dispatch productivo lo invoca Cloud Tasks server-to-server (sin RBAC). El front solo expone `dispatch-manual` (gated `BOT_ENGINE_INVOKE`) para debugging del admin. |
| `revalidateTag(TAG, "max")` (2º arg) | Next 16 exige el 2º argumento; omitirlo es error (lección del template). Todos los actions lo pasan. |
| Tags por-recurso anidado + cross-tag | `bots:versions:{id}`/`bots:config-tools:{id}`/`bots:debug:{cid}` evitan invalidar todos al mutar uno; crear/activar versión cruza con `bots:configurations` (el `current_version_*` denormalizado). |
| `brandPalette` sin `accent`; tokens semánticos | Lección transversal: colores de estado (error rojo/éxito verde) = tokens Fluent semánticos, no `brandPalette.accent` (no existe). |
| Sin bulk actions, sin import, sin tiempo real | Postergados al MVP+1 (igual que catalog/clinic/staff/crm/conversations). |

## Checklist de implementación (mapeado a fases F0–F4)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md#checklist-de-implementación) y [`ui.md`](./ui.md) (spec §8). Cada checkbox es lado frontend. **F4 (ExternalBotEngine + tools scheduling + handoff automático + streaming) está DIFERIDA** — fuera del MVP inicial.

### F0 — Prep (andamiaje compartido, sin migración)

- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `BOTS` (`BOT_CONFIGURATIONS` con list/create/get/update/delete/active + versions/version_get/activate_version + tools M:N; `BOT_TOOLS` con list/create/update/delete/active; `BOT_DEBUG` con state/state_reset/events/tool_calls; `BOT_ENGINE` con dispatch_manual). Verbos: `PUT` para config/tool update + tools M:N bulk; acciones `POST`; `/active` cruda. (`/engine/dispatch` OIDC y `/engine/external/*` NO van al front.)
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `bots` ("Bots" → Configuraciones `BOT_CONFIGURATIONS_READ`, Herramientas `BOT_TOOLS_READ`, Depuración `BOT_STATE_READ`; grupo gated `MENU-BOTS`).
- [ ] Registrar íconos `BotRegular`/`WrenchRegular`/`BugRegular` en el `iconMap` del `Sidebar.tsx` (con fallbacks verificados; `BotRegular` quizá ya está por conversations).
- [ ] Crear `src/types/bots.types.ts` (TODAS las interfaces + enums bots-owned; **reusa** `UserAuditInfo` de audit.types; `input_message_id`/`output_message_id` = `string | null`; `cost_estimated_usd` = `string`).
- [ ] Crear `src/lib/constants/bots.ts` (`BOT_TYPE_META`, `BOT_PROVIDER_META`, `PROVIDER_MODEL_PRESETS`, `BOT_EVENT_TYPE_META`, `TOOL_CALL_STATUS_META`).
- [ ] Skeleton inerte (NO registrar pages/actions reales — solo types/endpoints/nav/constants). Los Settings nuevos del backend (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`BOT_DEFAULT_MODEL`/`CLOUD_TASKS_*`/`MAX_TOOL_ITERATIONS_PER_TURN`) **NO** tienen contraparte de env en el front (no hay `NEXT_PUBLIC_*` de bots — todo es server-side del backend).
- [ ] **Permisos test (F0)**: como ADMIN, el grupo "Bots" aparece con Configuraciones + Herramientas + Depuración. Como ASESOR (`MENU-BOTS` + reads), aparece Configuraciones + Depuración (NO Herramientas). Sin `MENU-BOTS` (DOCTOR), el grupo no aparece. (Los 14 permisos + roles ya están en `seed.py` — ver [`../_seed-and-roles.md`](../_seed-and-roles.md), backend F0.)

### F1 — BotConfiguration + Version + activate-version

- [ ] Crear `src/lib/schemas/bot-configuration.schema.ts` (code slug/name/bot_type enum/description/max_turns_per_conversation?) + `bot-configuration-version.schema.ts` (system_prompt no-vacío + provider enum + model_name + parameters JSON parseable + superRefine external_webhook_url).
- [ ] Crear `src/actions/bot-configuration.actions.ts` (CRUD config + versiones [list/get/create/activate] + tools M:N [get/set]; tags `bots:configurations`/`bots:versions:{id}`/`bots:config-tools:{id}`). (El M:N real se usa en F2 cuando exista el catálogo de tools; el action puede declararse acá.)
- [ ] Crear `src/app/(main)/bots/configuraciones/page.tsx` (`metadata.title = "Configuraciones de bots"`, prefetch `defaultSort = created_on desc`, `requirePermission("BOT_CONFIGURATIONS_READ")`) + `_components/BotConfigurationsClient.tsx` (tabla: name/code/bot_type badge/current_version "vN vigente"/max_turns/active; badge ámbar "Sin versión") + `BotConfigurationDrawer.tsx` (create/edit; sin API keys) + `BotVersionsPanel.tsx` (lista + Nueva versión + Activar) + `BotVersionEditor.tsx` (system_prompt textarea + provider/model selects + JSON editor parameters; read-only para versiones existentes + "Duplicar").
- [ ] **Smoke test (F1)**: `/bots/configuraciones` → "Nuevo bot" (code/name/bot_type) → aparece con badge "Sin versión vigente" → abrir Versiones → "Nueva versión" (system_prompt + provider=openai + model gpt-4.1-mini + parameters `{"temperature":0.7}`) → crear → "Activar" → la fila muestra "v1 vigente" → crear una v2 (cambiar prompt) → activar v2 → la v1 queda en el historial (inmutable).
- [ ] **Error test (F1)**: crear bot con code duplicado → `409 BOT_CONFIGURATION_CODE_TAKEN`; crear versión con JSON de parameters inválido → error inline Zod (no llega al server); activar una versión que no es del bot → `400 BOT_VERSION_NOT_OWNED`; (si se forzara) provider=external_webhook sin URL → `EXTERNAL_WEBHOOK_URL_REQUIRED` (el select lo deshabilita en el MVP).
- [ ] **Permisos test (F1)**: sin `BOT_CONFIGURATIONS_CREATE` no aparece "Nuevo bot"; sin `_UPDATE` no aparece Editar; sin `_DELETE` no aparece Eliminar; sin `BOT_CONFIGURATION_VERSIONS_WRITE` no aparece "Nueva versión"/"Activar" (solo ver); el ASESOR ve la tabla read-only.

### F2 — BotTool + M:N + catálogo de tools

- [ ] Crear `src/lib/schemas/bot-tool.schema.ts` (code slug/name/description obligatoria/parameters_schema JSON parseable/target_service formato/requires_confirmation/is_active).
- [ ] Crear `src/actions/bot-tool.actions.ts` (list/active/create/update/delete; tag `bots:tools`).
- [ ] Crear `src/app/(main)/bots/tools/page.tsx` (`metadata.title = "Herramientas de bots"`, `requirePermission("BOT_TOOLS_READ")`, prefetch `defaultSort = created_on desc`) + `_components/BotToolsClient.tsx` (tabla: name/code/target_service/requires_confirmation/is_active) + `BotToolDrawer.tsx` (create/edit; description obligatoria; JSON editor parameters_schema; target_service formato).
- [ ] Cablear `BotToolsAssignment.tsx` (editor M:N de tools del bot, molde `StatusMatrixEditor`/`SearchableOptionList`; `getBotConfigurationTools` + `listActiveBotTools` → multiselect → `setBotConfigurationTools` bulk) y enlazarlo desde la RowAction "Herramientas" de `BotConfigurationsClient`.
- [ ] **Smoke test (F2)**: `/bots/tools` → "Nueva herramienta" (code `list_verticals` + description + target_service `catalog.vertical.list_active` + parameters_schema `{}`) → aparece en la tabla → crear `set_lead_status` (requires_confirmation=true) → desde `/bots/configuraciones`, abrir Herramientas de un bot → multiselect preselecciona ninguna → seleccionar `list_verticals` + `set_lead_status` → guardar → recargar persiste el set.
- [ ] **Error test (F2)**: crear tool con code duplicado → `409 BOT_TOOL_CODE_TAKEN`; parameters_schema con JSON inválido → error inline Zod; (runtime, no en este test) target_service no registrado → `TOOL_NOT_REGISTERED` 404 al dispatchar.
- [ ] **Permisos test (F2)**: sin `BOT_TOOLS_WRITE` no aparece "Nueva herramienta"/Editar/Eliminar (solo ver con `BOT_TOOLS_READ`); el ASESOR NO ve `/bots/tools` (sin `BOT_TOOLS_READ` → redirige).

### F3 — Engine + State + Events + ToolCalls + depuración (completa el bot MVP)

- [ ] Crear `src/actions/bot-debug.actions.ts` (getState `T|null`/listEvents/listToolCalls/resetState/dispatchManual; tag `bots:debug:{conversationId}`).
- [ ] Crear `src/app/(main)/bots/depuracion/page.tsx` (`metadata.title = "Depuración de bots"`, `requirePermission("BOT_STATE_READ")`, deep-link `?c=` → `Promise.all([getBotState, listBotEvents, listBotToolCalls])`; estado vacío sin `?c=`) + `_components/BotDebugShell.tsx` (orquesta state/events/tool-calls a demanda + "Actualizar" + "Reiniciar estado" [BOT_STATE_WRITE] + "Disparar turno" [BOT_ENGINE_INVOKE]) + `BotStateCard.tsx` (intent/slots/turn_count/versión; JSON viewer de slots) + `BotEventTimeline.tsx` (turnos agrupados por día client-only, memoizado; tokens/latencia/costo/error) + `BotEventRow.tsx` (memoizada) + `BotToolCallList.tsx` (args/result/status, JSON viewers read-only).
- [ ] **Smoke test (F3)**: con un bot configurado + activado en un canal (enganche conversations: `channel_account.bot_configuration_id` set → la conversación nueva arranca `assignee_type='bot'`), enviar un WhatsApp real al número → el webhook encola la Cloud Task → el bot responde (outbound real vía `send_bot_outbound`) → en `/conversaciones/bandeja?c=<cid>` la burbuja del bot aparece (en vivo por Firestore, dominio de conversations) → en `/bots/depuracion?c=<cid>` el `BotStateCard` muestra turn_count≥1 + intent/slots → el `BotEventTimeline` muestra `turn_started`/`turn_completed` con tokens/latencia/costo → si el turno usó tools, `BotToolCallList` muestra los args/result/status.
- [ ] **Dispatch manual test (F3)**: como ADMIN con `BOT_ENGINE_INVOKE`, "Disparar turno" en una conversación bot → el backend encola/dispara → "Actualizar" tras unos segundos muestra el nuevo turno en el timeline. Sin `BOT_ENGINE_INVOKE` el botón no aparece.
- [ ] **Reset state test (F3)**: "Reiniciar estado" (gated `BOT_STATE_WRITE`) con confirm → slots/intent/turn_count se borran → `BotStateCard` muestra "Sin datos recolectados". Sobre una conversación no-bot → `400 CONVERSATION_NOT_BOT` en `MessageBar`.
- [ ] **Estado null test (F3)**: depurar una conversación cuyo bot nunca corrió un turno → `getBotState` devuelve null → "El bot aún no ha actuado en esta conversación." (no error).
- [ ] **TZ test (F3)**: con el reloj cerca de medianoche en TZ Lima (`-05:00`), un turno de "hoy" aparece bajo "Hoy" (no "Ayer") en el timeline — confirma agrupación client-only.
- [ ] **Permisos test (F3)**: sin `BOT_STATE_READ` la Depuración redirige; sin `BOT_STATE_WRITE` no aparece "Reiniciar estado"; sin `BOT_ENGINE_INVOKE` no aparece "Disparar turno"; `BOT_EVENTS_READ`/`BOT_TOOL_CALLS_READ` gatean el timeline/tool-calls (el ASESOR los tiene → ve la depuración read-only). El link "Ver conversación" solo si `CONVERSATIONS_READ`.

### F4 — ExternalBotEngine + tools scheduling + handoff automático + streaming (DIFERIDA, fuera del MVP)

- [ ] Habilitar `provider=external_webhook` en el select del `BotVersionEditor` (mostrar los campos `external_webhook_url/secret_name`) cuando el `ExternalBotEngine` + `/engine/external/*` existan (spec §0.2). Hoy deshabilitado "(no disponible aún)".
- [ ] Agregar las tools de scheduling (`book_appointment`/`check_availability`/`cancel_appointment`) al catálogo cuando scheduling #7 las registre en el `TOOL_REGISTRY` (hoy NO seedeadas → no aparecen — spec §0.4).
- [ ] UI de handoff automático (el bot escala a humano cuando lo decide), streaming de la respuesta del bot, cost cap duro, eval framework — fuera del MVP inicial (spec §8 F4).

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog**. Para `bots` no hay deuda de traducción del template — todos los strings nuevos nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Configuraciones de bots", "Herramientas de bots", "Depuración de bots").
- [ ] Todos los `label` de `NAV_ITEMS.bots` en español ("Bots", "Configuraciones", "Herramientas", "Depuración").
- [ ] Glosario UI: **Bot · Configuración · Versión · Vigente · Herramienta · Proveedor · Modelo · Prompt del sistema · Parámetros · Turno · Tokens · Latencia · Costo estimado · Estado del bot · Intención · Datos recolectados · Reiniciar estado · Disparar turno · Requiere confirmación** — usados consistentemente en badges, botones, empty states, confirm dialogs.
- [ ] Empty states/placeholders en español: "Sin versión vigente", "Crea y activa una versión para que el bot pueda atender.", "Selecciona una conversación para depurar", "El bot aún no ha actuado en esta conversación.", "El bot aún no ha tenido turnos en esta conversación.", "El bot no ha invocado herramientas en esta conversación.", "Sin datos recolectados", "No hay herramientas en el catálogo.".
- [ ] Mensajes de error de dominio que vienen del backend ya en español (`BOT_CONFIGURATION_NOT_FOUND`, `BOT_CONFIGURATION_CODE_TAKEN`, `BOT_VERSION_NOT_FOUND`, `BOT_VERSION_NOT_OWNED`, `NO_CURRENT_VERSION`, `EXTERNAL_WEBHOOK_URL_REQUIRED`, `BOT_TOOL_NOT_FOUND`, `BOT_TOOL_CODE_TAKEN`, `TOOL_NOT_REGISTERED`, `PROVIDER_NOT_SUPPORTED`, `BOT_STATE_NOT_FOUND`, `CONVERSATION_NOT_BOT`) — los `detail` se devuelven en español para mostrarse directo; el `code` queda en inglés (coordinar con [`backend.md`](./backend.md#códigos-de-error) / spec §7). `BOT_PROVIDER_ERROR` es interno (log; el dispatch no devuelve 5xx al front).

## TODOs deliberados (postergados al MVP+1)

- [ ] **F4 — ExternalBotEngine** (provider external_webhook + `/engine/external/*`) — diseñado en el contrato (campos en las entidades/tipos), engine y endpoints diferidos (spec §0.2 / §8).
- [ ] **Tools de scheduling** (`book_appointment`/`check_availability`/`cancel_appointment`) — diseñadas pero NO seedeadas hasta que scheduling #7 las registre (spec §0.4).
- [ ] **Editor de código real para JSON** (Monaco/CodeMirror con syntax highlight + autocompletado) en `parameters`/`parameters_schema` — el MVP usa textarea + `JSON.parse`. Agrega peso de bundle.
- [ ] **Validar `parameters_schema` como JSON Schema válido** (ajv meta-schema) en el editor — el MVP solo valida JSON parseable a objeto.
- [ ] **JSON tree-viewer** (colapsable/expandible) para `collected_slots`/`arguments`/`result`/`metadata` — el MVP usa `<pre>` + `JSON.stringify`.
- [ ] **Grilla/diff de versiones** (comparar v2 vs v3 del system_prompt) — el MVP lista versiones + "Duplicar como base".
- [ ] **Resolver `input_message_id`/`output_message_id` al contenido del mensaje** (vista del mensaje inline en la depuración) — hoy referencia opaca + link al hilo de conversations.
- [ ] **Real-time/auto-refresh de la depuración** (re-fetch tras un turno sin "Actualizar" manual) — el MVP recarga a demanda; el turno corre server-side por Cloud Tasks.
- [ ] **Métricas/dashboard del bot** (tokens/costo agregados por bot/período, tasa de handoff, intents más frecuentes) — fuera del MVP de configuración + depuración.
- [ ] **Ruteo preventa/postventa por `crm.PersonCustomerStatus`** (`choose_bot_for_conversation` avanzado) — el MVP usa `channel_account.bot_configuration_id` (spec §3).
- [ ] **Cost cap duro** (cortar el bot al superar un presupuesto) — el MVP tiene `max_turns_per_conversation` (guard de turnos) + `MAX_TOOL_ITERATIONS_PER_TURN` (env backend), pero no cap de USD (spec §0.9).
