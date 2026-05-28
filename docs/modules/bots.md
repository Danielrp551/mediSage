# Módulo `bots`

> **Última actualización**: 2026-05-28
> **Propósito**: motor conversacional configurable — configuración, versionado, estado por conversation, tools invocables y traza de turnos.
> **Path del código**: `backend/app/modules/bots/`

## Resumen

`bots` modela **el cerebro** que atiende automáticamente las conversaciones cuando el `Conversation.assignee_type = bot`. El módulo es **agnóstico al motor de ejecución**: las entidades (configuración, estado, tools, traza) están listas para que el LLM corra **dentro del backend medisage** (engine embebido) **o en un servicio externo** (engine remoto que escribe vía API/webhooks).

Decisión documentada en [ADR-005](../decisions/ADR-005-agnostic-bot-engine.md).

```
┌──────────────────────────────────────────────────────────────────┐
│ conversations.services.webhook_processor.process_inbound(...)    │
│   ↓ persiste Message inbound                                      │
│   ↓ si Conversation.assignee_type == 'bot':                       │
│       bots.services.engine.dispatch_turn(conversation, message)   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
       ┌───────────────────┴────────────────────┐
       ▼                                        ▼
┌──────────────────┐                  ┌──────────────────────────┐
│ EmbeddedEngine   │                  │ ExternalEngine           │
│ (in-process LLM) │                  │ (POST a webhook externo) │
└────────┬─────────┘                  └────────┬─────────────────┘
         │                                      │
         │ ambos: persisten BotEvent,           │
         │ leen/escriben ConversationBotState,  │
         │ ejecutan BotToolCall si aplica       │
         │                                      │
         ▼                                      ▼
    ┌────────────────────────────────────────────────┐
    │ conversations.services.message.send_outbound() │
    └────────────────────────────────────────────────┘
```

**Handoff**: confirmado por usuario que en MVP es **solo manual** — el bot no decide derivar al asesor por sí mismo. El asesor toma desde el inbox vía `POST /conversations/{id}/take`, lo que cambia `assignee_type='advisor'`; a partir de ahí, los inbound siguen llegando al backend pero `bots.dispatch_turn` no se invoca (porque `conversations` filtra por `assignee_type='bot'`).

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `BotConfiguration` | `bot_configuration` | Bot lógico (preventa, postventa, ...). Apunta a su versión vigente. |
| `BotConfigurationVersion` | `bot_configuration_version` | Versión del prompt y parámetros. Permite rollback y A/B testing. |
| `ConversationBotState` | `conversation_bot_state` | Estado en curso del bot por conversation (intent, slots, turn_count). |
| `BotTool` | `bot_tool` | Catálogo de funciones invocables por el bot. |
| `BotToolCall` | `bot_tool_call` | Traza inmutable de cada invocación de tool. |
| `BotEvent` | `bot_event` | Traza inmutable por turno: tokens, latencia, errores, mensajes I/O. |
| _(M:N)_ `bot_configuration_tool` | `bot_configuration_tool` | Qué tools puede usar cada bot. |

### `BotConfiguration`

Bot lógico que opera la clínica. Una clínica típica tiene `preventa` y `postventa` como mínimo, pero podría tener más (uno por vertical, por canal, por idioma).

- `code: varchar(40)` `<<unique>>` — slug (`preventa_estetica`, `postventa_dental`).
- `name: varchar(120)` — nombre humano.
- `bot_type: varchar(20)` — enum cerrado: `preventa / postventa / general / custom`. `general` para casos sin distinción. `custom` para casos no estándar.
- `description: text` `<<nullable>>`.
- `current_version_id: varchar(36)` `<<nullable, FK→bot_configuration_version>>` — la versión vigente. `NULL` mientras no haya ninguna creada (estado de bot recién bootstrapeado, no usable hasta crear versión).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `BotConfigurationVersion`

Versión inmutable del prompt + parámetros + provider + modelo. Permite A/B testing y rollback.

- `bot_configuration_id: varchar(36)` `<<FK→bot_configuration>>`.
- `version: int` — secuencial dentro del bot. UNIQUE `(bot_configuration_id, version)`. Service incrementa al crear.
- `system_prompt: text` — el prompt completo del system.
- `provider: varchar(40)` — `claude / openai / vertex_ai / azure_openai / langchain / external_webhook / ...`. Determina qué cliente usa el engine embebido. `external_webhook` significa que el motor externo se ocupa (provider de elección lo decide el equipo del bot externo).
- `model_name: varchar(120)` — `claude-opus-4-7`, `gpt-4`, `gemini-1.5-pro`, etc. Texto libre porque la lista cambia.
- `parameters: jsonb` — `{temperature, max_tokens, top_p, ...}`. Schema libre porque varía por provider.
- `external_webhook_url: varchar(500)` `<<nullable>>` — solo para `provider='external_webhook'`. URL del servicio externo que ejecuta turnos.
- `external_webhook_secret_name: varchar(255)` `<<nullable>>` — secret name en GCP Secret Manager para autenticar el webhook (HMAC u OAuth token bearer).
- `notes: text` `<<nullable>>` — changelog del prompt (por qué se cambió).
- `is_active: bool` `default true` — soft-disabled si se quiere mantener la versión pero no usar (no es el `current_version_id`).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Promoción de versión**: editar el `system_prompt` o `parameters` de una versión existente NO es el flujo esperado. Se crea una versión nueva (`version = max + 1`) y se promueve con `POST /bot-configurations/{id}/activate-version/{version_id}`. El service:
1. Valida que la versión pertenezca al bot.
2. Actualiza `bot_configuration.current_version_id = version_id`.
3. Registra `LeadActivity`/audit log según se considere (queda libre, no es CRM activity).

### `ConversationBotState`

Estado mutable del bot para una `Conversation`. UNIQUE por `conversation_id`.

- `conversation_id: varchar(36)` `<<unique, FK→conversation>>`.
- `bot_configuration_id: varchar(36)` `<<FK→bot_configuration>>`.
- `bot_configuration_version_id: varchar(36)` `<<FK→bot_configuration_version>>` — versión con la que se inició el state. Si la conversación corre y se promueve una nueva versión del bot, el state **no se migra automáticamente** — sigue con la versión que arrancó. Decisión: estabilidad por conversación. Si admin quiere forzar, llama a `POST /conversations/{id}/bot-state/reset` que crea un state nuevo con la `current_version_id` actual.
- `current_intent: varchar(80)` `<<nullable>>` — interés detectado (`agendar_cita`, `consultar_precio`, `pedir_info_general`, ...). Es texto libre (no FK a catálogo) porque cada bot define su propia taxonomía de intents en el prompt.
- `collected_slots: jsonb` — datos recolectados del lead durante la conversación (`{"nombre": "Juan", "vertical_interesada": "dental", "fecha_preferida": "2026-06-10"}`). Schema libre por bot.
- `last_node: varchar(120)` `<<nullable>>` — paso del flow si el bot implementa state machine; `NULL` para bots LLM puros.
- `last_bot_turn_at: timestamptz` `<<nullable>>`.
- `turn_count: int` `default 0` — contador de turnos del bot en la conversación.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `BotTool`

Catálogo de funciones invocables por el bot. Cada tool tiene un schema JSON Schema (compatible con OpenAI/Claude tool calling) y apunta a un service del backend que la ejecuta.

- `code: varchar(60)` `<<unique>>` — `book_appointment`, `check_availability`, `list_products_by_vertical`, `register_lead_note`, `update_lead_status`, `cancel_appointment`.
- `name: varchar(120)` — nombre humano.
- `description: text` — descripción **usada por el LLM** para decidir cuándo invocar la tool. Crítica: si está mal redactada, el bot no la usa o la usa mal.
- `parameters_schema: jsonb` — JSON Schema de los argumentos. Ejemplo para `book_appointment`:
  ```json
  {
    "type": "object",
    "properties": {
      "doctor_id": {"type": "string", "description": "ID del doctor"},
      "product_id": {"type": "string", "description": "ID del producto/servicio"},
      "scheduled_for": {"type": "string", "format": "date-time"},
      "person_id": {"type": "string"}
    },
    "required": ["doctor_id", "product_id", "scheduled_for", "person_id"]
  }
  ```
- `target_service: varchar(120)` — referencia interna al service que ejecuta. Formato: `<module>.<service>.<function>` (ej. `scheduling.appointment.create_from_bot`). El dispatcher del engine resuelve este string a la función Python real (vía registry).
- `requires_confirmation: bool` `default false` — si la tool altera estado (agendar, cancelar), el bot debe confirmar con el usuario antes de invocar. El engine inyecta este flag en el prompt para que el LLM sepa cuándo confirmar.
- `is_active: bool` `default true`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**M:N con BotConfiguration** vía `bot_configuration_tool` — el bot preventa puede usar `book_appointment` y `list_products_by_vertical`, pero no `cancel_appointment` (que es de postventa).

**Seguridad**: el target_service ejecuta con permisos de "sistema" (NO con `CurrentAuth`), pero tiene que validar reglas de negocio. Documentar en cada service de tool que es entrypoint sin auth-context. Patrón: cada service de tool recibe `bot_invocation_context: BotInvocationContext` con `conversation_id`, `person_id`, `bot_tool_call_id` para audit.

### `BotToolCall`

Traza inmutable de cada invocación de tool. Permite depurar "qué hizo el bot en esta conversación".

- `conversation_id: varchar(36)` `<<FK→conversation>>`.
- `bot_event_id: varchar(36)` `<<nullable, FK→bot_event>>` — turno al que pertenece.
- `bot_tool_id: varchar(36)` `<<FK→bot_tool>>`.
- `tool_use_id: varchar(255)` `<<nullable>>` — id que el LLM asigna al tool_use block (para `tool_result` matching en multi-tool turns). Cuando aplica.
- `arguments: jsonb` — args con los que se llamó.
- `result: jsonb` `<<nullable>>` — resultado serializado. `NULL` mientras está pending o si falló.
- `status: varchar(20)` — `pending / success / error / timeout`.
- `error_message: text` `<<nullable>>`.
- `started_at: timestamptz`.
- `completed_at: timestamptz` `<<nullable>>`.
- `latency_ms: int` `<<nullable>>`.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — traza inmutable.

### `BotEvent`

Traza inmutable por turno. Confirmado por usuario que va al MVP.

- `conversation_id: varchar(36)` `<<FK→conversation>>`.
- `bot_configuration_id: varchar(36)` `<<FK→bot_configuration>>`.
- `bot_configuration_version_id: varchar(36)` `<<FK→bot_configuration_version>>`.
- `turn_number: int` — secuencial por conversation (1, 2, 3, ...). UNIQUE `(conversation_id, turn_number)`.
- `event_type: varchar(40)` — `turn_started / turn_completed / turn_failed / tool_dispatched / handoff_triggered`. Enum cerrado.
- `input_message_id: varchar(36)` `<<nullable, FK→message>>` — mensaje inbound que disparó el turno.
- `output_message_id: varchar(36)` `<<nullable, FK→message>>` — mensaje outbound emitido como respuesta. `NULL` si el turno no produjo respuesta (ej. solo tool_call sin user-facing message).
- `tokens_in: int` `<<nullable>>`.
- `tokens_out: int` `<<nullable>>`.
- `latency_ms: int` `<<nullable>>`.
- `cost_estimated_usd: numeric(10,6)` `<<nullable>>` — calculado por el engine según provider/model rates en config.
- `error: text` `<<nullable>>`.
- `metadata: jsonb` `<<nullable>>` — payload específico del provider (raw response, model fingerprint, etc.).
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — traza inmutable.

## Esquemas (Pydantic v2)

Variantes habituales por entidad. Específicos del módulo:

- `BotConfigurationDetail` extiende `BotConfigurationItem` con `current_version: BotConfigurationVersionItem?` y `versions_count: int`.
- `BotConfigurationVersionCreate` no acepta `version` — el service lo asigna (`max + 1` por bot).
- `ActivateVersionRequest { version_id: str }` — body de POST `/bot-configurations/{id}/activate-version`.
- `ConversationBotStateItem` lleva `current_version: BotConfigurationVersionOption` y `last_event: BotEventOption?` para debugging UI.
- `DispatchTurnRequest { conversation_id, input_message_id }` — body opcional para forzar dispatch desde admin.
- `ResetBotStateRequest { reason? }` — body de POST `/conversations/{id}/bot-state/reset`.

## Endpoints

Bajo `/api/v1/bots/`.

### Configuration

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/configurations/list` | `BOT_CONFIGURATIONS_READ` |
| `POST` | `/configurations` | `BOT_CONFIGURATIONS_CREATE` |
| `GET` | `/configurations/{id}` | `BOT_CONFIGURATIONS_READ` |
| `PATCH` | `/configurations/{id}` | `BOT_CONFIGURATIONS_UPDATE` |
| `DELETE` | `/configurations/{id}` | `BOT_CONFIGURATIONS_DELETE` |
| `GET` | `/configurations/options?bot_type=` | `BOT_CONFIGURATIONS_READ` |

### Configuration Versions

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/configurations/{id}/versions` | `BOT_CONFIGURATION_VERSIONS_READ` | listar (paginado simple) |
| `POST` | `/configurations/{id}/versions` | `BOT_CONFIGURATION_VERSIONS_WRITE` | crear nueva versión |
| `GET` | `/configurations/{id}/versions/{version_id}` | `BOT_CONFIGURATION_VERSIONS_READ` |
| `POST` | `/configurations/{id}/activate-version/{version_id}` | `BOT_CONFIGURATION_VERSIONS_WRITE` | promover versión a current |

### Tools

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/tools/list` | `BOT_TOOLS_READ` |
| `POST` | `/tools` | `BOT_TOOLS_WRITE` |
| `PATCH` | `/tools/{id}` | `BOT_TOOLS_WRITE` |
| `DELETE` | `/tools/{id}` | `BOT_TOOLS_WRITE` |
| `GET` | `/configurations/{id}/tools` | `BOT_CONFIGURATIONS_READ` | tools asignados al bot |
| `PUT` | `/configurations/{id}/tools` | `BOT_CONFIGURATIONS_UPDATE` | bulk replace de M:N (body: `{tool_ids: list[str]}`) |

### State / Events / Tool Calls

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/conversations/{conversation_id}/state` | `BOT_STATE_READ` |
| `POST` | `/conversations/{conversation_id}/state/reset` | `BOT_STATE_WRITE` |
| `GET` | `/conversations/{conversation_id}/events` | `BOT_EVENTS_READ` |
| `GET` | `/conversations/{conversation_id}/tool-calls` | `BOT_TOOL_CALLS_READ` |

### Engine

| Método | Ruta | Auth | Propósito |
|---|---|---|---|
| `POST` | `/engine/dispatch-turn` | JWT, admin only (`BOT_ENGINE_INVOKE`) | dispara turno manualmente (debugging) |
| `POST` | `/engine/choose-for-conversation/{conversation_id}` | sistema (interno desde `conversations`) | retorna `bot_configuration_id` apropiado según estado de Person (preventa vs postventa) |
| `POST` | `/engine/external/callback` | HMAC sig | endpoint para que un engine **externo** entregue la respuesta del turno (cuando `provider='external_webhook'`) |
| `POST` | `/engine/external/tool-result` | HMAC sig | engine externo entrega resultado de un tool que el backend ejecutó |

**Nota sobre `/engine/external/*`**: cuando `provider='external_webhook'`, el flujo es:
1. `bots.engine.dispatch_turn` POST al `external_webhook_url` con el contexto del turno.
2. El servicio externo ejecuta el LLM y responde con `{message_to_send, tool_calls?}`.
3. Si pidió tools, el backend las ejecuta y vuelve a llamar al externo con los resultados.
4. Cuando termina, el externo POST a `/engine/external/callback` con la respuesta final.

## Permisos seed

```python
# Module: bots
("MENU-BOTS", "Ver menú bots", "Configuración y depuración de bots", "bots"),
("BOT_CONFIGURATIONS_READ", "Ver bots", "Listar configuraciones de bot", "bots"),
("BOT_CONFIGURATIONS_CREATE", "Crear bots", "Crear nueva configuración", "bots"),
("BOT_CONFIGURATIONS_UPDATE", "Editar bots", "Editar configuración y M:N de tools", "bots"),
("BOT_CONFIGURATIONS_DELETE", "Eliminar bots", "Soft-delete de configuración", "bots"),
("BOT_CONFIGURATION_VERSIONS_READ", "Ver versiones del bot", "Consultar versiones del prompt", "bots"),
("BOT_CONFIGURATION_VERSIONS_WRITE", "Editar versiones del bot", "Crear/promover versiones", "bots"),
("BOT_TOOLS_READ", "Ver catálogo de tools", "Listar tools del bot", "bots"),
("BOT_TOOLS_WRITE", "Editar catálogo de tools", "CRUD del catálogo de tools", "bots"),
("BOT_STATE_READ", "Ver estado del bot por conversación", "Consultar ConversationBotState", "bots"),
("BOT_STATE_WRITE", "Resetear estado del bot", "Forzar reset del state de una conversación", "bots"),
("BOT_EVENTS_READ", "Ver eventos del bot", "Consultar traza de turnos (tokens, latencia)", "bots"),
("BOT_TOOL_CALLS_READ", "Ver llamadas a tools", "Consultar traza de tool calls", "bots"),
("BOT_ENGINE_INVOKE", "Invocar engine manualmente", "Disparar turno desde admin (debugging)", "bots"),
```

**Roles seed que tocan `bots`**:
- `ADMIN` — todos.
- `ASESOR` — `BOT_CONFIGURATIONS_READ` (saber qué bot atiende), `BOT_STATE_READ`, `BOT_EVENTS_READ`, `BOT_TOOL_CALLS_READ` (depurar conversaciones que tomó). **No** edita config ni invoca engine.
- `DOCTOR` — sin permisos en este módulo.

## Decisiones de diseño

### Motor agnóstico (embebido vs externo) — ver [ADR-005](../decisions/ADR-005-agnostic-bot-engine.md)
La interfaz `BotEngine` con implementaciones `EmbeddedBotEngine` y `ExternalBotEngine`. Las entidades del módulo son las mismas en ambos casos — solo cambia quién ejecuta el LLM.

### Versionado de prompts via `BotConfigurationVersion`
Confirmado por usuario. Cada cambio de prompt/parameters/provider es una **nueva versión**, no edit in-place. La versión vigente es `bot_configuration.current_version_id`. Permite:
- Rollback rápido (`POST /activate-version`).
- A/B testing futuro (asignar versiones distintas a conversaciones según criterio).
- Estabilidad por conversación: una conversación que inició con v3 no cambia a v4 a media charla — el `ConversationBotState.bot_configuration_version_id` queda fijo.

### Tools en BD (no hard-coded)
Confirmado por usuario. Permite agregar/quitar tools sin deploy, y mantiene traza de quién las invocó cuándo con qué args.

**Trade-off**: el `target_service` apunta a una función Python por **string**. El dispatcher mantiene un `TOOL_REGISTRY: dict[str, Callable]` que mappea code → función. Si admin agrega una tool con `target_service` no registrado, el dispatcher lanza error claro. Esto evita que admin "inscriba" tools que no existen en código.

### Handoff manual, sin criterios automáticos en BotConfiguration
Confirmado por usuario. El bot no decide derivar — el asesor toma cuando ve la conversación. Implicancia: el bot debe ser bueno en decir "no sé" o "espera un momento" sin loopear. Si en MVP+1 se quiere handoff automático, se agregan columnas a `BotConfiguration` (`handoff_after_failed_intents`, `handoff_keywords`) — diseño aditivo, no rompe el modelo.

### `BotEvent` en MVP
Confirmado. Sin observabilidad del bot, no se puede mejorar el bot. Cada turno deja traza:
- ¿Cuántos tokens consumió este bot esta semana?
- ¿Qué turnos tuvieron error?
- ¿Latencia P95 del bot?
- ¿Qué tool falló más?

Indexes sugeridos: `(conversation_id, turn_number)`, `(bot_configuration_id, created_on)`, `(event_type, created_on)`.

### `ConversationBotState` no se resetea automáticamente al promover versión
Estabilidad por conversación. La conversación que arrancó con v3 sigue con v3 hasta cerrar. Si admin quiere migrar, llama `POST /state/reset` explícitamente. Evita inconsistencias mid-conversation.

### `ConversationBotState.collected_slots` como JSONB libre
Cada bot define su propio schema de slots en el system_prompt. El backend no impone estructura. Si en el futuro se quiere validar, agregar `slot_schema` en `BotConfigurationVersion`.

### `BotTool.target_service` como string + TOOL_REGISTRY
La alternativa "FK a una tabla de services" no aplica porque los services son funciones Python, no entidades. La alternativa "guardar el código Python serializado" es un agujero de seguridad. El string + registry es el patrón estándar (similar a `webhook_processor/<canal>.py`).

### Engine externo via webhook con HMAC
Confirmado en respuesta sobre credenciales (Secret Manager). El secret_name del webhook externo vive en `BotConfigurationVersion.external_webhook_secret_name`. El backend firma sus requests salientes con HMAC; el externo firma sus callbacks con HMAC. Patrón estándar para integraciones de IA externos.

## Flujo de un turno del bot (engine embebido)

1. `conversations.process_inbound` persiste `Message` y, si `assignee_type='bot'`, invoca `bots.services.engine.dispatch_turn(conversation, message, db)`.
2. **dispatch_turn**:
   1. Carga `ConversationBotState` (o lo crea si no existe).
   2. Carga `BotConfigurationVersion` que el state apunta.
   3. Inserta `BotEvent(event_type='turn_started', turn_number=state.turn_count+1, input_message_id=msg.id)`.
   4. Construye el prompt: `system_prompt` + historia de mensajes (`Message`) + slots actuales + tools disponibles (`bot_configuration_tool` ∩ active).
   5. Invoca el provider (`claude.messages.create()` o similar) con tool definitions.
   6. **Si el LLM pide tools**:
      - Inserta `BotToolCall(status='pending', arguments=..., tool_use_id=...)`.
      - Llama `TOOL_REGISTRY[tool.code](arguments, BotInvocationContext)`.
      - Update `BotToolCall(status='success' | 'error', result=..., latency_ms, completed_at)`.
      - Loop al step 5 con los tool_results en el prompt.
   7. **Mensaje de respuesta**: persiste outbound vía `conversations.services.message.send_outbound(...)` que retorna `output_message_id`.
   8. Update `ConversationBotState.{last_node, last_bot_turn_at, turn_count, collected_slots}` (slots se extraen del razonamiento del LLM).
   9. Update `BotEvent(event_type='turn_completed', output_message_id, tokens_in, tokens_out, latency_ms, cost_estimated_usd)`.
3. Errores en cualquier paso → `BotEvent(event_type='turn_failed', error=str)` + el engine puede enviar un mensaje de fallback o silenciar (configurable en parameters).

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `conversations` | `ChannelAccount.bot_configuration_id`, `Conversation.bot_configuration_id`, `Message.bot_configuration_id` (FKs). El módulo `conversations` invoca `bots.engine.dispatch_turn` en el flow inbound. |
| `crm` | `bots.engine.choose_bot_for_conversation` lee `PersonCustomerStatus` para decidir preventa/postventa. Las tools del bot pueden invocar services de `crm` (registrar nota, transicionar lead status). |
| `scheduling` | Tools del bot invocan `scheduling.appointment.create_from_bot`, `check_availability`. |
| `catalog` | Tools invocan `list_products_by_vertical`. |
| `admin` | Audit users via mixins; permisos via RBAC. |

## Diagramas

- ER: [`docs/diagrams/er-bots.puml`](../diagrams/er-bots.puml)
- Class: [`docs/diagrams/class-backend-bots.puml`](../diagrams/class-backend-bots.puml)

## Próximos pasos / TODOs deliberados

- [ ] **`TOOL_REGISTRY` runtime**: al implementar, registrar tools en `app/modules/bots/services/tool_registry.py` con `@register_tool("book_appointment")`. El service `dispatch_turn` resuelve.
- [ ] **BotInvocationContext**: dataclass con `conversation_id`, `person_id`, `bot_configuration_id`, `bot_tool_call_id`. Inyectado en cada tool service. Documentar el contrato.
- [ ] **Rate limit y costo cap**: agregar `BotConfiguration.max_cost_per_conversation_usd` para frenar el bot si una conversación se vuelve excesivamente cara. Postergado hasta tener data real de costos.
- [ ] **Streaming**: cuando MVP UI quiera ver al bot "tipear", usar SSE desde el outbound endpoint. Postergado.
- [ ] **Eval framework**: tests de regresión del prompt — inputs conocidos → outputs esperados. Cuando lleguemos a producción real, evaluar `promptfoo` o similar.
- [ ] **Handoff automático**: si los reportes muestran loops del bot, agregar columnas a BotConfiguration (`handoff_after_failed_intents: int`, `handoff_keywords: text[]`). Postergado por decisión del usuario.
