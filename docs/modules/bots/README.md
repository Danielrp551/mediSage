# Módulo `bots`

> **Última actualización**: 2026-06-04 (fase de documentación, ANTES de implementar — reconcilia el diseño viejo `docs/modules/bots.md`/[ADR-005](../../decisions/ADR-005-agnostic-bot-engine.md) de 2026-05-28 con la realidad post-Firestore/CQRS, la lección async (Cloud Tasks) y el orden real de implementación; ver [Reconciliaciones](#reconciliaciones-autoritativo--no-re-litigar))
> **Propósito**: el **cerebro conversacional configurable** de la clínica. Atiende automáticamente las conversaciones de WhatsApp con un **LLM** cuando `Conversation.assignee_type='bot'` — responde info, captura/transiciona leads y notas, lista catálogo — y entrega el hilo a un humano cuando el asesor lo **toma**. Es **agnóstico al motor** ([ADR-005](../../decisions/ADR-005-agnostic-bot-engine.md)): MVP **embebido multi-proveedor** (OpenAI default + Claude), motor externo diseñado pero diferido. Es el **módulo #6** del proyecto — se construye sobre `conversations` (#5), `crm` (#4), `catalog` (#1) y `admin`; `scheduling` (#7) se enganchará vía **tools** cuando exista.
> **Path del código**: `backend/app/modules/bots/` (backend, incl. `services/engine/` con adaptadores por proveedor) · `frontend/src/app/(main)/bots/` (frontend). El endpoint **interno** `POST /api/v1/bots/engine/dispatch` lo invoca **Cloud Tasks** (OIDC, sin RBAC).

> **Este documento es el overview** (fuente de verdad consolidada del módulo; el overview viejo `docs/modules/bots.md` queda borrado y sus links repuntan aquí). Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts (request/response/errores), lógica de service, engine package (factory + adaptadores OpenAI/Claude), `TOOL_REGISTRY` + tools crm/catalog, `cloud_tasks.py`, draft SQL de las migraciones.
> - 🎨 [`ui.md`](ui.md) — mockups por pantalla con estados (empty/loading/no-results/error): configuraciones + editor de versiones/prompt, catálogo de tools + editor M:N por bot, y el **panel de depuración** del bot por conversación (la UI más pesada). UX writing en español.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación, types espejo.

## Resumen

`bots` es donde la clínica **automatiza** la primera línea de la conversación. Cuando entra un mensaje de WhatsApp en un canal que tiene un bot configurado, la conversación nace **asignada al bot** (`assignee_type='bot'`); el webhook de `conversations`, tras su pipe síncrono, **encola una Cloud Task**; un endpoint interno corre el **turno** del bot: arma el prompt (system prompt de la versión vigente + historial del hilo leído de **Firestore** + las tools habilitadas), llama al **LLM** (OpenAI `gpt-4.1-mini` por defecto, o Claude), corre el **loop de tool-calling** (resolver/transicionar leads en crm, listar catálogo) y emite la respuesta **outbound real** a Meta. Cada turno deja una traza auditable (`BotEvent` + `BotToolCall`). Cuando un asesor **toma** la conversación (handoff de `conversations` F3), pasa a `assignee_type='advisor'` y el bot **deja de responder** (el webhook solo encola la task si el hilo sigue en `bot`).

```
  Meta webhook  →  conversations.process_inbound  (persist_inbound + relay SÍNCRONO a Firestore)
        │
        │  si conv.assignee_type == 'bot':
        ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ bots.cloud_tasks.enqueue_turn(conversation_id, input_message_id)   │ ──▶ 200 a Meta
  │   (Transactional/at-least-once; cola qa/prod; reintentos+backoff+DLQ)│
  └───────────────────────────────┬──────────────────────────────────┘
                                  │  Cloud Task (request FRESCO, CPU asignada, OIDC)
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ POST /api/v1/bots/engine/dispatch   (auth OIDC/shared-secret, NO RBAC)│
  │   → bots.engine.dispatch_turn(conversation_id, input_message_id, db) │
  │   1. ConversationBotState (load-or-create) + BotConfigurationVersion vigente
  │   2. BotEvent(turn_started, turn_number, input_message_id=mid)       │
  │   3. prompt = system_prompt                                          │
  │        + historial del hilo (firestore.list_message_docs)  ──────────┼──▶ Firestore (read)
  │        + tools (bot_configuration_tool ∩ is_active)                  │
  │   4. engine_factory(version) → EmbeddedBotEngine.run(provider adapter)│
  │        provider: openai (gpt-4.1-mini) / claude                      │
  │   5. loop tool-calling (≤ MAX_TOOL_ITERATIONS_PER_TURN):             │
  │        BotToolCall(pending) → TOOL_REGISTRY[code](args, ctx) ─────────┼──▶ crm / catalog
  │        → BotToolCall(success|error) → re-prompt                      │
  │   6. conversations.message.send_bot_outbound(...) → output mid ──────┼──▶ Meta + Firestore
  │   7. update ConversationBotState (slots/intent/turn_count/last_turn) │
  │        + BotEvent(turn_completed, tokens/cost/latency)               │
  │   error → BotEvent(turn_failed) + mensaje de fallback (configurable) │
  └──────────────────────────────────────────────────────────────────┘
```

El bot **no toca la cola de mensajes** ni reimplementa el envío: **reusa** el pipe de `conversations` (Firestore para leer el hilo + `send_bot_outbound` para responder por la Graph API de Meta). Su trabajo propio es: elegir el bot del canal, mantener el **estado conversacional** por hilo (`ConversationBotState`), correr el LLM con sus **tools**, y dejar la **traza** (`BotEvent`/`BotToolCall`). El modelo nace **multi-proveedor** aunque el MVP cablee OpenAI + Claude: agregar Vertex AI / Azure OpenAI es un adaptador nuevo en `providers/` — sin migración (el enum `BotProvider` ya los lista; sin adaptador → `PROVIDER_NOT_SUPPORTED` en runtime).

## Posición y dependencias

`bots` es el **#6** del orden de medisage (catalog → clinic → staff → **crm** → **conversations** COMPLETOS en prod → **bots** → scheduling #7 → marketing #8). Depende de:

| Módulo | Relación | FK |
|---|---|---|
| `admin` | Audit users (`created_by`/`updated_by`) en las entidades de config; RBAC (14 permisos nuevos). El user `SYSTEM` (seed crm F0) es el `created_by` de los turnos automáticos del bot (no hay actor humano). | usa `user` (sin tabla nueva FK→user). |
| `conversations` (#5) | **Núcleo del enganche.** El bot corre **sobre** una `Conversation` con `assignee_type='bot'`: lee el historial del hilo desde **Firestore** (Admin SDK `firestore.list_message_docs`) y responde vía `message.send_bot_outbound`. `BotEvent`/`BotToolCall`/`ConversationBotState` tienen **FK real** → `conversation.id`. Se agregan **2 cambios aditivos** a conversations (engagement + outbound del bot) + **2 forward FK constraints** (`channel_account.bot_configuration_id`, `conversation.bot_configuration_id`). | **FK real** a `conversation`; **FK aditivas** a `channel_account`/`conversation` (ver [Enganche](#enganche-con-conversations-cambios-aditivos)). |
| `crm` (#4) | **Tools.** El bot resuelve/crea contacto (`person.find_by_identifier_or_create`), registra notas (`lead_activity.log(NOTE, related_conversation_id=...)`) y transiciona leads (`person_lead_status.transition`, valida la matriz). Lectura/escritura **vía tools**, no FK directa de bots a crm. | sin FK directa (las tools llaman services de crm). |
| `catalog` (#1) | **Tools.** El bot lista verticales/servicios/productos (`catalog.*.list_active`) para responder consultas de catálogo. Read-only, vía tools. | sin FK directa. |
| `scheduling` (#7, NO existe) | `book_appointment` / `check_availability` / `cancel_appointment` quedan **diseñadas** en la doc pero **NO seedeadas** (su `target_service` apuntaría a `scheduling.*` inexistente → `TOOL_NOT_REGISTERED` en runtime). Se cablean vía tools cuando #7 ship. | N/A (tools futuras). |

Migración cabeza actual = `0016_conv_threads` (última aplicada, de conversations F2). Las de bots: **`0017_bots_configuration`**, **`0018_bots_tools`**, **`0019_bots_engine_state`**.

## Arquitectura del motor — agnóstico ([ADR-005](../../decisions/ADR-005-agnostic-bot-engine.md))

Las **entidades** (configuración + versiones + estado + trazas) están **separadas de la implementación del engine**: el "qué/cómo responde" es un detalle de runtime, no del modelo. El paquete `app/modules/bots/services/engine/`:

- **`engine_factory(version) -> BotEngine`** — selecciona el engine por `BotConfigurationVersion.provider`. MVP: `openai`/`claude`/… embebidos → `EmbeddedBotEngine`; `external_webhook` → `ExternalBotEngine` **DIFERIDO** (`NotImplementedError` / `PROVIDER_NOT_SUPPORTED` en el MVP).
- **`BotEngine` (base)** — interfaz: `dispatch_turn(conversation_id, input_message_id, db)`, `choose_bot_for_conversation(conversation, db)`.
- **`EmbeddedBotEngine`** — orquesta el turno: arma el prompt, delega la llamada LLM al **adaptador del proveedor**, corre el **loop de tool-calling** (≤ `MAX_TOOL_ITERATIONS_PER_TURN`, default 5), persiste estado + trazas.
- **`providers/openai.py` / `providers/claude.py`** — un adaptador por proveedor con contrato común `complete(system, messages, tools, params) -> {text, tool_calls[], tokens_in, tokens_out}`. OpenAI usa el SDK `openai` (function calling); Claude usa `anthropic` (tool use + prompt caching del system prompt). Mapean las defs de tools ↔ el **subset común de JSON Schema** (OpenAI function calling ≈ Anthropic tool use).
- **`tools/__init__.py`** — `TOOL_REGISTRY: dict[str, Callable]` + decorator `@register_tool("code")` + dataclass `BotInvocationContext` (`conversation_id`, `person_id`, `bot_configuration_id`, `bot_tool_call_id`) inyectado en cada tool. Las tools **NO** reciben `CurrentAuth` (validan reglas sistémicas, p.ej. la matriz de transiciones de crm).
- **`tools/crm.py` / `tools/catalog.py`** — implementaciones MVP (ver [Tools](#tools-mvp-crm--catalog)).

> **Default model = `gpt-4.1-mini`** (OpenAI), parametrizable por versión (`model_name`, texto libre por proveedor) y por `Settings.BOT_DEFAULT_MODEL`. Las credenciales del proveedor son **globales por entorno** (`Settings.OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, inyectadas vía `--set-secrets` de Cloud Run); la resolución per-bot vía `secret_resolver` ([ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md)) queda para el futuro.

## Async del turno — Cloud Tasks ([ADR-012](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md))

El turno del bot llama a un LLM (segundos + loops de tool-calling) → es trabajo **lento, must-complete** que NO puede correr en el hot path del webhook (Meta reintenta si tarda) ni en `BackgroundTasks` (Cloud Run con `min-instances 0` + cpu-throttling no garantiza CPU tras el 200 — lección dura de conversations F2, donde el relay síncrono fue necesario). Decisión: **Cloud Tasks**.

- El webhook de `conversations`, **tras** su TX Postgres + relay Firestore síncrono, llama `bots.cloud_tasks.enqueue_turn(conversation_id, input_message_id)` **solo si** `conv.assignee_type == 'bot'`, y devuelve **200 a Meta**.
- La cola entrega un `POST /api/v1/bots/engine/dispatch` con **request fresco y CPU asignada**, autenticado por **OIDC / shared-secret** (NO RBAC — lo invoca la infra, no un usuario). Reintentos + backoff + DLQ + rate-limit configurados **por cola** (una por entorno: qa / prod).
- `app/core/cloud_tasks.py` — cliente **lazy** (no al import, para no romper el boot/smoke sin GCP) + helper `enqueue_turn`, molde de `app/core/secrets.py` / `app/core/firestore.py`.
- El dispatch **NO devuelve 5xx a Cloud Tasks** salvo para **forzar un reintento** controlado; los errores de proveedor se loguean (`BotEvent(turn_failed)`) + se emite un mensaje de fallback configurable, y se responde 200 (no reintentar un prompt que va a fallar igual).

## Entidades

Mixins: `PK`=`PrimaryKeyMixin` (id varchar(36)), `A`=`ActiveMixin` (active bool), `SD`=`SoftDeleteMixin` (deleted_at), `T`=`TimestampMixin` (created_on/by, updated_on/by). **Las trazas (`BotToolCall`, `BotEvent`) NO llevan `SD`** (audit inmutable — mismo criterio que `LeadStatusHistory`/`ConversationAssignmentLog`). `parameters`/`collected_slots`/`parameters_schema`/`arguments`/`result`/`metadata` usan `JSON().with_variant(JSONB, "postgresql")` (JSON en sqlite/create_all, JSONB en la migración Postgres — patrón `crm.lead_activity.payload`).

| Entidad | Tabla | Mixins | Propósito |
|---|---|---|---|
| `BotConfiguration` | `bot_configuration` | PK·A·SD·T | El bot como entidad de negocio (slug + tipo + versión vigente + guard de turnos). |
| `BotConfigurationVersion` | `bot_configuration_version` | PK·A·SD·T | Versión inmutable del prompt + provider + model + params. Editar = **nueva versión**, no in-place. |
| `ConversationBotState` | `conversation_bot_state` | PK·A·SD·T | Estado conversacional por hilo (intent/slots/turnos). `UNIQUE` por `conversation_id`. |
| `BotTool` | `bot_tool` | PK·A·SD·T | Catálogo de herramientas (JSON Schema + `target_service` resuelto por `TOOL_REGISTRY`). |
| `BotToolCall` | `bot_tool_call` | PK·A·T (SIN SD) | Traza inmutable de cada invocación de tool dentro de un turno (args/result/status/latencia). |
| `BotEvent` | `bot_event` | PK·A·T (SIN SD) | Traza inmutable por turno (tipo + tokens/costo/latencia + mids in/out). Audit + analítica. |
| M:N `bot_configuration_tool` | `bot_configuration_tool` | (PK compuesta) | Qué tools puede usar cada bot (`models/associations.py`). |

### `BotConfiguration`

El bot como entidad de negocio. Apunta a su **versión vigente** (`current_version_id`); sin versión vigente no es usable.

- `code: varchar(40)` — **UNIQUE parcial vivo** (`WHERE deleted_at IS NULL`). Slug (`preventa`, `postventa_dental`). Violación → `BOT_CONFIGURATION_CODE_TAKEN` (409).
- `name: varchar(120)` NOT NULL — nombre humano.
- `bot_type: varchar(20)` NOT NULL — enum `BotType` (`preventa` / `postventa` / `general` / `custom`).
- `description: text` nullable.
- `current_version_id: varchar(36)` nullable — **FK** → `bot_configuration_version.id`. La versión vigente; NULL = sin versión, no usable (dispatch/activate → `NO_CURRENT_VERSION` 400).
- `max_turns_per_conversation: int` nullable — guard opcional de costo/abuso (None = sin límite).

### `BotConfigurationVersion`

Versión **inmutable** del prompt + el proveedor/modelo/parámetros. La promoción de versión vigente se hace vía `activate-version` (no edición in-place del prompt).

- `bot_configuration_id: varchar(36)` NOT NULL — **FK** → `bot_configuration.id`.
- `version: int` NOT NULL — **UNIQUE `(bot_configuration_id, version)`**; el service asigna `max(version)+1`.
- `system_prompt: text` NOT NULL.
- `provider: varchar(40)` NOT NULL — enum `BotProvider` (`openai` / `claude` / `vertex_ai` / `azure_openai` / `external_webhook`). **MVP implementa `openai` (default) + `claude`**; el resto → `PROVIDER_NOT_SUPPORTED` (400) en runtime.
- `model_name: varchar(120)` NOT NULL — default **`gpt-4.1-mini`**; texto libre (depende del provider).
- `parameters: jsonb` — `{temperature?, max_tokens?, top_p?, ...}` (schema libre por provider; JSON-variant). `max_tokens` actúa como guard de costo por respuesta.
- `external_webhook_url: varchar(500)` nullable — **DIFERIDO**, solo `provider='external_webhook'`.
- `external_webhook_secret_name: varchar(255)` nullable — **DIFERIDO**.
- `notes: text` nullable — changelog del prompt.
- `is_active: bool` default true — soft-disable de la versión (distinto de "vigente": una versión puede estar `is_active=true` sin ser la `current`).
- **Validaciones service**: `provider='external_webhook'` ⇒ `external_webhook_url` requerido (`EXTERNAL_WEBHOOK_URL_REQUIRED` 400). La versión debe pertenecer al bot al activarla (`BOT_VERSION_NOT_OWNED` 400).

### `ConversationBotState`

Estado conversacional **por hilo** (memoria del bot entre turnos). Una fila por conversación.

- `conversation_id: varchar(36)` NOT NULL — **UNIQUE**, **FK** → `conversation.id`.
- `bot_configuration_id: varchar(36)` NOT NULL — **FK** → `bot_configuration.id`.
- `bot_configuration_version_id: varchar(36)` NOT NULL — **FK** → `bot_configuration_version.id`. La versión con la que arrancó el hilo; **NO se migra** al promover otra versión vigente (un hilo en curso mantiene su comportamiento; reset explícito vía `/state/reset`).
- `current_intent: varchar(80)` nullable — texto libre.
- `collected_slots: jsonb` — slots capturados (schema libre por bot; JSON-variant).
- `last_node: varchar(120)` nullable — para bots de flujo (forward).
- `last_bot_turn_at: timestamptz` nullable.
- `turn_count: int` NOT NULL default 0 — contra `max_turns_per_conversation`.

### `BotTool`

Catálogo de herramientas que el LLM puede invocar. La descripción la usa el LLM para decidir **cuándo** invocar; el `target_service` la resuelve el `TOOL_REGISTRY` en runtime.

- `code: varchar(60)` — **UNIQUE parcial vivo**. Violación → `BOT_TOOL_CODE_TAKEN` (409).
- `name: varchar(120)` NOT NULL.
- `description: text` NOT NULL — la lee el LLM (selección de tool).
- `parameters_schema: jsonb` NOT NULL — JSON Schema (subset común OpenAI/Anthropic; JSON-variant).
- `target_service: varchar(120)` NOT NULL — `<module>.<service>.<function>` resuelto por `TOOL_REGISTRY`. Si no está registrado → `TOOL_NOT_REGISTERED` (404) **en runtime** (NO al boot — el catálogo puede listar tools cuyo módulo no existe aún, p.ej. scheduling).
- `requires_confirmation: bool` default false — tools que mutan estado de negocio (p.ej. `set_lead_status`) pueden requerir confirmación.
- `is_active: bool` default true.

### `BotToolCall` (SIN SoftDelete — audit inmutable)

Traza de cada invocación de tool dentro de un turno.

- `conversation_id: varchar(36)` NOT NULL — **FK** → `conversation.id`.
- `bot_event_id: varchar(36)` nullable — **FK** → `bot_event.id` (el turno que la disparó).
- `bot_tool_id: varchar(36)` NOT NULL — **FK** → `bot_tool.id`.
- `tool_use_id: varchar(255)` nullable — id del `tool_use` del LLM (matching multi-tool en un mismo turno).
- `arguments: jsonb` NOT NULL — args con que el LLM invocó (JSON-variant).
- `result: jsonb` nullable — resultado serializado (JSON-variant).
- `status: varchar(20)` NOT NULL — enum `ToolCallStatus` (`pending` / `success` / `error` / `timeout`).
- `error_message: text` nullable.
- `started_at: timestamptz` NOT NULL · `completed_at: timestamptz` nullable · `latency_ms: int` nullable.

### `BotEvent` (SIN SoftDelete — audit inmutable)

Traza **por turno**. Es la base de la depuración y de la analítica de costo.

- `conversation_id: varchar(36)` NOT NULL — **FK** → `conversation.id`.
- `bot_configuration_id: varchar(36)` NOT NULL — **FK** → `bot_configuration.id`.
- `bot_configuration_version_id: varchar(36)` NOT NULL — **FK** → `bot_configuration_version.id`.
- `turn_number: int` NOT NULL — **UNIQUE `(conversation_id, turn_number)`**.
- `event_type: varchar(40)` NOT NULL — enum `BotEventType` (`turn_started` / `turn_completed` / `turn_failed` / `tool_dispatched` / `handoff_triggered`).
- **`input_message_id: varchar(255)` nullable** — el `mid` (doc-id Firestore) del inbound que disparó el turno. **NO es FK** (no hay tabla `message`; los mensajes viven en Firestore — [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md)).
- **`output_message_id: varchar(255)` nullable** — el `mid` del outbound emitido (lo devuelve `send_bot_outbound`). **NO es FK**.
- `tokens_in: int` nullable · `tokens_out: int` nullable · `latency_ms: int` nullable.
- `cost_estimated_usd: numeric(10,6)` nullable.
- `error: text` nullable.
- `metadata: jsonb` nullable — raw provider response / fingerprint (JSON-variant).
- **Índices**: `(conversation_id, turn_number)` UNIQUE · `(bot_configuration_id, created_on)` · `(event_type, created_on)`.

### M:N `bot_configuration_tool` (`models/associations.py`)

`bot_configuration_id` (FK) + `bot_tool_id` (FK), **PK compuesta**. Define qué tools puede usar cada bot. Se edita por `PUT /configurations/{id}/tools` (bulk, `{tool_ids:[]}`).

## Enums (en código)

`app/modules/bots/enums.py`, `StrEnum` (ruff `UP042`):

| Enum | Valores |
|---|---|
| `BotType` | `preventa`, `postventa`, `general`, `custom` |
| `BotProvider` | `openai`, `claude`, `vertex_ai`, `azure_openai`, `external_webhook` (MVP implementa `openai`+`claude`) |
| `BotEventType` | `turn_started`, `turn_completed`, `turn_failed`, `tool_dispatched`, `handoff_triggered` |
| `ToolCallStatus` | `pending`, `success`, `error`, `timeout` |

> El bot **lee** `Conversation.assignee_type` (enum `AssigneeType` de conversations: `bot`/`advisor`/`unassigned`) — lo importa de `app.modules.conversations.enums`, **NO** lo duplica (single source of truth, igual que conversations reusa `crm.ChannelType`).

## Tools MVP (crm + catalog)

Seedeadas en `TOOL_REGISTRY` (código, vía `@register_tool`) **y** en el catálogo `bot_tool` (BD, asignables M:N por bot). Las tools reciben `(args, ctx: BotInvocationContext)` y llaman el service del módulo dueño — **sin** `CurrentAuth` (validan reglas sistémicas, p.ej. la matriz de transiciones).

| Tool (`code`) | `target_service` | Qué hace |
|---|---|---|
| `list_verticals` | `catalog.vertical.list_active` | Lista verticales (read). |
| `list_services_by_vertical` | `catalog.service.list_active` | Lista servicios de una vertical (read). |
| `list_products_by_vertical` | `catalog.product.list_active` | Lista productos de una vertical (read). |
| `register_lead_note` | `crm.lead_activity.log` | Registra una nota en el timeline del lead (`NOTE`, `related_conversation_id=ctx.conversation_id`). |
| `set_lead_status` | `crm.person_lead_status.transition` | Transiciona el lead (valida la **matriz** de crm; `requires_confirmation=true`). |
| `resolve_or_create_contact` | `crm.person.find_by_identifier_or_create` | Resuelve/crea el contacto (idempotente; advisory lock). |

**DIFERIDAS (NO seedear en el MVP — su `target_service` apunta a `scheduling.*` inexistente)**: `book_appointment`, `check_availability`, `cancel_appointment`. Quedan **diseñadas en la doc**; se cablean cuando `scheduling` (#7) ship (sin migración — son filas nuevas en `bot_tool` + entries en el `TOOL_REGISTRY`).

## Enganche con `conversations` (cambios aditivos)

`bots` agrega **2 cambios aditivos backward-compatible** al service de `conversations` + **2 forward FK constraints**. Sin esto, hoy `conversations` nunca asigna a un bot ni deja que un bot responda (las columnas `bot_configuration_id` existen pero son siempre NULL — forward FK [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md)).

### 1. Engagement del bot (conversación nueva nace en `bot`)

Hoy `conversations.find_or_create_open` asigna a advisor (dueño del lead) / unassigned, **nunca a bot**. **Cambio aditivo**: si `channel_account.bot_configuration_id` está set, las conversaciones **nuevas** de ese canal arrancan `assignee_type='bot'`, `assignee_user_id=NULL`, `bot_configuration_id=<el del canal>` (en vez de la auto-asignación al asesor). Sin bot configurado en el canal → comportamiento actual **intacto**. El `ConversationAssignmentLog` inicial registra `to_assignee_type='bot'`, `by_actor_user_id=NULL` (automático).

### 2. Outbound del bot (`send_bot_outbound`)

Hoy `conversations.message.send_outbound` exige `assignee_type=='advisor'` + `actor==assignee` → un bot daría `NOT_CONVERSATION_ASSIGNEE`. **Cambio aditivo**: `message.send_bot_outbound(db, conversation, content, *, bot_configuration_id)` — valida `assignee_type=='bot'` (NO el advisor-assignee check), escribe `sender_type='bot'`, `sender_user_id=None`, `bot_configuration_id` en el doc Firestore; reusa el **mismo** Meta Graph API + outbox + relay síncrono que el outbound humano. Devuelve el `mid` outbound (→ `BotEvent.output_message_id`).

### 3. Handoff: el asesor "le quita" el hilo al bot

El `take` del asesor (conversations F3) cambia `assignee_type` a `'advisor'` → el webhook **deja de encolar** la task del bot (solo encola si `assignee_type=='bot'`). El bot **deja de responder** sin código nuevo en conversations (la condición de engagement ya lo cubre). Recíprocamente, un `release` a `bot` (futuro, requiere `bot_configuration_id`) devolvería el hilo al bot. El handoff **del bot al humano** dispara un `BotEvent(handoff_triggered)`.

### 4. Forward FK constraints (la migración F1 las agrega)

`conversations` dejó las columnas `channel_account.bot_configuration_id` y `conversation.bot_configuration_id` como **forward FK** (`varchar(36)` sin constraint/relationship — ADR-009). La migración **F1** de bots las **promueve a FK reales** (Postgres-only, aditivo):

```python
op.create_foreign_key("fk_channel_account_bot_configuration", "channel_account", "bot_configuration", ["bot_configuration_id"], ["id"])
op.create_foreign_key("fk_conversation_bot_configuration", "conversation", "bot_configuration", ["bot_configuration_id"], ["id"])
```

**SIN** `relationship` ORM (acceso por id + batch maps — lección crm; no romper el mapper de conversations). Seguro: todos los valores actuales son NULL. Caveat sqlite: el `ALTER ADD FK` no corre en sqlite/create_all (la migración solo corre en Postgres; el smoke usa create_all → no ejercita la FK aditiva).

## Endpoints (resumen)

Todos bajo `/api/v1/bots/` (aggregator `app/modules/bots/routers/__init__.py` con `APIRouter(prefix="/bots")`, incluido en `main.py`, molde conversations) — **salvo** `/engine/dispatch`, que es **top-level interno** (target de Cloud Tasks, sin RBAC). Convención: **`PUT` (no `PATCH`)**; **`POST /<recurso>/list`** para listados paginados; **`/active`** para dropdowns. El detalle de request/response/errores está en [`backend.md`](backend.md#api-contracts).

| Método | Ruta | Permiso | Notas |
|---|---|---|---|
| POST | `/configurations/list` | `BOT_CONFIGURATIONS_READ` | `PaginatedResponse[BotConfigurationItem]`. `defaultSort = created_on desc` |
| POST | `/configurations` | `BOT_CONFIGURATIONS_CREATE` | `SingleResponse[BotConfigurationDetail]` |
| GET | `/configurations/active` | `BOT_CONFIGURATIONS_READ` | lista cruda `BotConfigurationOption` (dropdown del canal) |
| GET | `/configurations/{id}` | `BOT_CONFIGURATIONS_READ` | `SingleResponse[BotConfigurationDetail]` |
| PUT | `/configurations/{id}` | `BOT_CONFIGURATIONS_UPDATE` | code/name/bot_type/description/max_turns |
| DELETE | `/configurations/{id}` | `BOT_CONFIGURATIONS_DELETE` | soft-delete |
| GET | `/configurations/{id}/versions` | `BOT_CONFIGURATION_VERSIONS_READ` | lista de versiones del bot |
| POST | `/configurations/{id}/versions` | `BOT_CONFIGURATION_VERSIONS_WRITE` | crea nueva versión (`max+1`); editar prompt = versión nueva |
| GET | `/configurations/{id}/versions/{vid}` | `BOT_CONFIGURATION_VERSIONS_READ` | detalle de versión |
| POST | `/configurations/{id}/activate-version/{vid}` | `BOT_CONFIGURATION_VERSIONS_WRITE` | promueve a `current_version_id` (valida ownership) |
| POST | `/tools/list` | `BOT_TOOLS_READ` | `PaginatedResponse[BotToolItem]` |
| POST | `/tools` | `BOT_TOOLS_WRITE` | crea tool |
| PUT | `/tools/{id}` | `BOT_TOOLS_WRITE` | edita tool |
| DELETE | `/tools/{id}` | `BOT_TOOLS_WRITE` | soft-delete |
| GET | `/configurations/{id}/tools` | `BOT_CONFIGURATIONS_READ` | tools asignadas al bot (M:N) |
| PUT | `/configurations/{id}/tools` | `BOT_CONFIGURATIONS_UPDATE` | bulk M:N `{tool_ids:[]}` |
| GET | `/conversations/{cid}/state` | `BOT_STATE_READ` | `SingleResponse[ConversationBotStateDetail]` |
| POST | `/conversations/{cid}/state/reset` | `BOT_STATE_WRITE` | resetea slots/intent/turn_count + versión vigente |
| GET | `/conversations/{cid}/events` | `BOT_EVENTS_READ` | timeline de `BotEvent` (depuración) |
| GET | `/conversations/{cid}/tool-calls` | `BOT_TOOL_CALLS_READ` | `BotToolCall` del hilo (depuración) |
| POST | `/engine/dispatch` | **OIDC/shared-secret (NO RBAC)** | **top-level interno**, target de Cloud Tasks; body `{conversation_id, input_message_id?}` |
| POST | `/engine/dispatch-manual` | `BOT_ENGINE_INVOKE` | encola/dispara un turno para **debugging** (admin) |

> `/engine/external/*` (motor externo) **DIFERIDO** — no se implementan en el MVP.

> **`ALLOWED_FIELDS`** (lección hotfix `cd10c78` de staff): solo columnas reales de cada tabla. `defaultSort` de configuraciones = `created_on desc`. Los denormalizados (nombre de versión vigente, etc.) **NO** son sortable/filterable server-side.

> **Códigos de error de dominio** (`detail` en **español**, `code` en inglés): `BOT_CONFIGURATION_NOT_FOUND` (404) · `BOT_CONFIGURATION_CODE_TAKEN` (409) · `BOT_VERSION_NOT_FOUND` (404) · `BOT_VERSION_NOT_OWNED` (400) · `NO_CURRENT_VERSION` (400, activar/dispatch sin versión vigente) · `EXTERNAL_WEBHOOK_URL_REQUIRED` (400) · `BOT_TOOL_NOT_FOUND` (404) · `BOT_TOOL_CODE_TAKEN` (409) · `TOOL_NOT_REGISTERED` (404, runtime — `target_service` sin entry en el registry) · `PROVIDER_NOT_SUPPORTED` (400, provider sin adaptador en el MVP) · `BOT_STATE_NOT_FOUND` (404) · `CONVERSATION_NOT_BOT` (400, dispatch sobre un hilo que no está en `assignee_type='bot'`) · `BOT_PROVIDER_ERROR` (interno, log — el dispatch NO devuelve 5xx a Cloud Tasks salvo para forzar reintento). La tabla con el "cuándo" exacto está en [`backend.md`](backend.md).

## Permisos seed

**14 permisos.** Ya canónicos en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md) — **no se redefinen aquí, se referencian**. F0 los agrega a `SEED_PERMISSIONS`:

```
MENU-BOTS ·
BOT_CONFIGURATIONS_{READ,CREATE,UPDATE,DELETE} ·
BOT_CONFIGURATION_VERSIONS_{READ,WRITE} ·
BOT_TOOLS_{READ,WRITE} ·
BOT_STATE_{READ,WRITE} ·
BOT_EVENTS_READ · BOT_TOOL_CALLS_READ ·
BOT_ENGINE_INVOKE
```

**Roles seed que tocan `bots`** (subsets canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md#matriz-roles--permisos)):

- `ADMIN` — **todos** los 14 (configurar bots/versiones/tools + depurar + dispatch manual).
- `ASESOR` — **read-only**: `BOT_CONFIGURATIONS_READ`, `BOT_STATE_READ`, `BOT_EVENTS_READ`, `BOT_TOOL_CALLS_READ` (ve qué hace el bot en sus conversaciones, no lo configura).
- `DOCTOR` — **sin** permisos en bots.

> El endpoint `/engine/dispatch` **NO usa RBAC** (lo invoca Cloud Tasks con OIDC/shared-secret). `BOT_ENGINE_INVOKE` gatea solo el **dispatch manual** de admin (debugging). El turno automático corre con `created_by = SYSTEM` (no hay actor humano).

## Frontend (resumen)

UI 100% en español. Fluent UI 9 (tokens semánticos; **sin** `brandPalette.accent`). Nav grupo **"Bots"** (`MENU-BOTS`):

- **"Configuraciones"** (`/bots/configuraciones`, `BOT_CONFIGURATIONS_READ`) — DataTable + drawer (code/name/bot_type/description/max_turns) + **tab Versiones** (lista + crear versión con editor de `system_prompt`/`provider`/`model_name`/`parameters` + botón **"Activar"** que promueve la versión vigente).
- **"Tools"** (`/bots/tools`, `BOT_TOOLS_READ`) — DataTable + drawer (code/name/description/`parameters_schema` [editor JSON]/`target_service`/`requires_confirmation`) + editor M:N de tools por bot (multiselect, molde `StatusMatrixEditor`/`SearchableOptionList` de crm).
- **"Depuración"** — panel **read-only** por conversación (se entra desde el inbox de conversations o desde la config): `ConversationBotState` (intent/slots/turn_count/versión) + **timeline de `BotEvent`** (tokens/latencia/costo/error por turno) + `BotToolCall` (args/result/status). Es la **UI más pesada** del módulo (como el timeline de crm / el inbox de conversations). Reusar molde conversations.

El detalle completo (mockups por pantalla con estados, glosario, componentes Fluent) está en [`ui.md`](ui.md) y [`frontend.md`](frontend.md).

Glosario UI: Bot · Configuración · Versión · Activar versión · Prompt del sistema · Proveedor · Modelo · Parámetros · Herramienta (tool) · Esquema de parámetros · Requiere confirmación · Estado del bot · Intención · Datos capturados (slots) · Turno · Evento del turno · Tokens · Costo estimado · Latencia · Llamada a herramienta · Depuración.

## Implementación por fases

Una fase por grupo cohesivo. Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist mapeado a estas fases. Migraciones revid ≤ 32 chars (límite `alembic_version varchar(32)`; clinic F3 reventó con 34). Última aplicada = `0016_conv_threads`.

| Fase | Alcance | Migración (revid ≤32) |
|---|---|---|
| **F0 — Prep** | 14 perms BOTS → `SEED_PERMISSIONS` (ya canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md)) + asignar a ADMIN/ASESOR (auto-expand); nav grupo "Bots" + iconos (Configuraciones / Tools / Depuración) gated `MENU-BOTS`; `endpoints.ts` (bloque bots) + `types/bots.types.ts` (espejo completo, inerte); skeleton backend inerte (`models/schemas/repositories/services/routers/__init__.py` + `services/engine/` con docstrings). **Settings nuevos** (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`BOT_DEFAULT_MODEL`/`CLOUD_TASKS_*`/`MAX_TOOL_ITERATIONS_PER_TURN`). **NO** registrar en `app/modules/__init__.py` ni `main.py` (lo cablea F1). | ninguna (solo seed) |
| **F1 — BotConfiguration + Version + activate-version** | tablas `bot_configuration` + `bot_configuration_version` (UNIQUE parciales dialect-agnósticos) + **forward FK constraints aditivas** a `channel_account`/`conversation` (Postgres-only); backend CRUD config + versiones + promoción; registrar `bots` en `app/modules/__init__.py` + aggregator router en `main.py`; UI `/bots/configuraciones` (tabla + drawer + tab Versiones + activar). (Sin engine/tools aún.) | `0017_bots_configuration` (24) ✓; down_revision `0016_conv_threads` |
| **F2 — BotTool + M:N + `TOOL_REGISTRY` + tools crm/catalog** | tablas `bot_tool` + `bot_configuration_tool` (M:N); CRUD catálogo de tools + asignación M:N por bot; `services/engine/tools/` (`TOOL_REGISTRY` + `@register_tool` + `BotInvocationContext`) + `tools/crm.py` + `tools/catalog.py` (reales); UI `/bots/tools` + editor M:N de tools del bot. | `0018_bots_tools` (15) ✓; down_revision `0017_bots_configuration` |
| **F3 — Engine + State + Events + ToolCalls + Cloud Tasks + enganches conversations** | tablas `conversation_bot_state` + `bot_event` + `bot_tool_call`; `EmbeddedBotEngine` (adaptadores `providers/openai.py` + `providers/claude.py`) + `dispatch_turn` + loop tool-calling (≤ `MAX_TOOL_ITERATIONS_PER_TURN`) + `/engine/dispatch` (OIDC) + `/engine/dispatch-manual` (RBAC) + `app/core/cloud_tasks.py`; **enganches conversations** (`find_or_create_open`→bot + `message.send_bot_outbound`) + provider creds (`--set-secrets` en AMBOS workflows) + **infra Cloud Tasks** (cola qa/prod + IAM OIDC). UI de **depuración** por conversación (state + timeline `BotEvent` + tool calls). **Completa el bot MVP** (preventa/info + captura de lead, embebido OpenAI/Claude). | `0019_bots_engine_state` (22) ✓; down_revision `0018_bots_tools` |
| **F4 — DIFERIDA** | `ExternalBotEngine` + `/engine/external/*`; tools `scheduling.*` (tras #7); handoff **automático** (el bot decide pasar a humano); streaming; cost cap **duro**; eval framework. Fuera del MVP. | (a definir en F4) |

> Flujo de cada fase = el de la metodología: leer fichas → backend e2e + smoke (sqlite create_all, RESULT=PASS + conteo a stdout) → frontend e2e (subagente contexto fresco) → tsc + build → review adversaria (Workflow 4 dims → verificación por hallazgo) → commit limpio (sin Co-Authored-By) → ff develop→qa → QA E2E con limpieza → **gate de usuario (AskUserQuestion separado del merge)** → prod → PROD read-only → actualizar memoria. Backend venv: `backend/.venv/Scripts/{python,ruff,mypy}.exe`.

## Reconciliaciones (autoritativo — NO re-litigar)

Consolidación de la §0 de la spec (decisiones confirmadas con el usuario 2026-06-04). Reconcilian el diseño viejo (`docs/modules/bots.md` + [ADR-005](../../decisions/ADR-005-agnostic-bot-engine.md) de 2026-05-28, **anterior** al rediseño Firestore/CQRS, a la lección async, y al orden real de implementación). **Este README gana**; al implementar, alinear `backend.md`/`ui.md`/`frontend.md` a esto.

1. **Async del turno = Cloud Tasks** (NO `BackgroundTasks`, NO síncrono). El webhook de conversations, tras su pipe síncrono, **encola una Cloud Task**; el endpoint interno `POST /api/v1/bots/engine/dispatch` (OIDC/shared-secret, NO RBAC) corre `dispatch_turn` con CPU asignada. Reintentos + backoff + DLQ + rate-limit por cola. → **[ADR-012](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md)** (nuevo). `app/core/cloud_tasks.py` (cliente lazy + enqueue, molde `secrets.py`/`firestore.py`).
2. **Motor = Embedded multi-proveedor** (OpenAI default `gpt-4.1-mini` + Claude + extensible). `EmbeddedBotEngine` con **adaptadores por proveedor** (`providers/openai.py`, `providers/claude.py`) seleccionados por `BotConfigurationVersion.provider`. Contrato de tools = **subset común JSON Schema** (OpenAI function calling ≈ Anthropic tool use). **`ExternalBotEngine` DISEÑADO pero DIFERIDO**: las entidades llevan `provider`/`external_webhook_url`/`external_webhook_secret_name`, pero **NO** se implementa el código del engine externo ni los endpoints `/engine/external/*` en el MVP (aditivo después, sin migración).
3. **Mensajes en Firestore (CQRS, [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md)), NO Postgres**: NO hay tabla `message`. `BotEvent.input_message_id`/`output_message_id` son **`varchar(255)` planos = el `mid` (doc-id Firestore)**, NO FK→message. El bot **lee el historial del hilo desde Firestore** (Admin SDK `firestore.list_message_docs`) para armar el prompt. El doc Firestore del mensaje outbound lleva el campo `bot_configuration_id` (lo setea `send_bot_outbound`).
4. **Tools = crm + catalog SOLO** (scheduling #7 aún no existe). El MVP: responde info + registra/transiciona leads y notas (crm) + lista verticales/servicios/productos (catalog) + resuelve/crea contacto. `book_appointment`/`check_availability`/`cancel_appointment` quedan **DISEÑADAS pero NO seedeadas** (su `target_service` apuntaría a `scheduling.*` inexistente → `TOOL_NOT_REGISTERED` en runtime). Se cablean cuando scheduling ship.
5. **Engagement del bot** (gap del diseño viejo): hoy `conversations.find_or_create_open` asigna a advisor/unassigned, **nunca a bot**. **Cambio aditivo a conversations**: si `channel_account.bot_configuration_id` está set, las conversaciones NUEVAS de ese canal arrancan `assignee_type='bot'` con ese bot. El `take` del asesor (F3) cambia a `assignee_type='advisor'` → el bot deja de responder (el webhook solo encola la task si `assignee_type=='bot'`). Sin bot configurado en el canal → comportamiento actual intacto.
6. **Outbound del bot** (gap): `conversations.message.send_outbound` exige `assignee_type=='advisor'` + actor==assignee → un bot daría `NOT_CONVERSATION_ASSIGNEE`. **Cambio aditivo a conversations**: `message.send_bot_outbound(db, conversation, content, *, bot_configuration_id)` — valida `assignee_type=='bot'`, `sender_type='bot'`, `sender_user_id=None`, `bot_configuration_id` en el doc; reusa el mismo Meta Graph API + outbox + relay síncrono. Devuelve el `mid` outbound (→ `BotEvent.output_message_id`).
7. **Credenciales de proveedor**: `Settings.OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (**global por entorno**, vía `--set-secrets` de Cloud Run; resolución per-bot vía `secret_resolver` [ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md) = futuro). Agregar a `--set-env-vars`/`--set-secrets` de **ambos** workflows de deploy. Deps runtime: `openai>=1.x`, `anthropic>=0.40` (ya está por conversations).
8. **Forward FK constraints**: la migración de **F1** agrega aditivamente (Postgres-only, [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md)) `ALTER TABLE channel_account ADD CONSTRAINT ... FK bot_configuration_id → bot_configuration.id` y `ALTER TABLE conversation ADD CONSTRAINT ... FK bot_configuration_id → bot_configuration.id`. **SIN** `relationship` ORM (acceso por id + batch maps, lección crm — no romper el mapper de conversations).
9. **Guards de costo/seguridad** (no estaban): `MAX_TOOL_ITERATIONS_PER_TURN` (default 5) corta loops de tool-calling; `BotConfigurationVersion.parameters` puede llevar `max_tokens`. `BotConfiguration.max_turns_per_conversation` (nullable) = guard opcional. **Cost cap duro = diferido** (F4).
10. **`BotEvent`/`BotToolCall` SIN SoftDelete** (audit inmutable, mismo criterio que `LeadStatusHistory`/`ConversationAssignmentLog`). El turno automático corre con `created_by = SYSTEM`.
11. **`ConversationBotState.bot_configuration_version_id` NO se migra al promover** otra versión vigente (un hilo en curso mantiene su comportamiento; reset explícito vía `/state/reset`).
12. **`AssigneeType`/`ChannelType` se reusan, no se duplican** — bots importa `AssigneeType` de `conversations.enums`; las tools de catalog/crm consumen los services/enums de esos módulos.

## Diagramas

- ER: [`docs/diagrams/er-bots.puml`](../../diagrams/er-bots.puml)
- Class diagram (modelos + repos + services + engine package + tools + cloud_tasks): [`docs/diagrams/class-backend-bots.puml`](../../diagrams/class-backend-bots.puml)

> Ambos diagramas se **(re)generan al modelo de esta spec** en la consolidación post-fichas (lo hace el implementador): **ER** = las 7 entidades (`bot_configuration`, `bot_configuration_version`, `conversation_bot_state`, `bot_tool`, `bot_tool_call`, `bot_event`) + M:N `bot_configuration_tool`; `channel_account`/`conversation`/`person`/`vertical` como **externos punteados** (`<<external>>`); anotar `input_message_id`/`output_message_id` = `mid` Firestore (NO FK), las forward FK aditivas a `channel_account`/`conversation`, y `AssigneeType` reuse. **Class** = `models` + `repositories` + `services` + el package `services/engine/` (`engine_factory`, `BotEngine` base, `EmbeddedBotEngine`, `providers/{openai,claude}.py`, `tools/__init__.py` con `TOOL_REGISTRY`/`BotInvocationContext`, `tools/{crm,catalog}.py`) + `app/core/cloud_tasks.py`; anotar el consumo de `conversations.firestore.list_message_docs` + `message.send_bot_outbound`, y de los services crm/catalog vía tools. Usar `PUT` (no `PATCH`) en toda referencia.

## Próximos pasos / TODOs deliberados

- [ ] **Consolidación post-fichas** (la hace el implementador): actualizar [ADR-005](../../decisions/ADR-005-agnostic-bot-engine.md) (Accepted, sección "Actualización 2026-06-04": Firestore-no-message-FK, Cloud Tasks async dispatch, embedded multi-proveedor OpenAI default, external diferido, enganches conversations) + crear **[ADR-012](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md)** (Accepted, "Cloud Tasks para el dispatch del turno del bot"); actualizar el índice [`docs/decisions/README.md`](../../decisions/README.md); regenerar `er-bots.puml` + `class-backend-bots.puml` al modelo de esta spec + actualizar el índice [`docs/diagrams/README.md`](../../diagrams/README.md); borrar el overview viejo `docs/modules/bots.md` y repuntar TODOS sus links (`grep "modules/bots.md"`) a este README; crear `project_medisage_bots_plan.md` + puntero en MEMORY.md.
- [ ] **Cambios aditivos sobre conversations** (al implementar F3): `find_or_create_open`→bot (engagement) + `message.send_bot_outbound` + las **2 forward FK constraints** (`channel_account`/`conversation`). Documentarlo como TODO en el overview de conversations (la FK aditiva la agrega bots, no conversations).
- [ ] **Infra Cloud Tasks** (F3): crear la cola por entorno (qa / prod) + IAM (SA invoker con OIDC para `/engine/dispatch`) + envs `CLOUD_TASKS_*`. Cliente SDK **lazy** (no romper el boot/smoke sin GCP).
- [ ] **Provider creds** (F3): crear/poblar `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` por entorno (Secret Manager → `--set-secrets`) en **ambos** workflows de deploy + `BOT_DEFAULT_MODEL=gpt-4.1-mini`.
- [ ] **Cuando `scheduling` (#7) ship**: seedear `book_appointment`/`check_availability`/`cancel_appointment` (filas `bot_tool` + entries `TOOL_REGISTRY`, sin migración) y asignarlas a los bots que corresponda.
- [ ] **F4 (diferida)**: `ExternalBotEngine` + `/engine/external/*`; handoff automático (el bot decide pasar a humano); streaming; cost cap duro; eval framework de prompts.
