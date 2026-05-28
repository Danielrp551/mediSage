# ADR-005: Motor del bot agnóstico — entidades de bot separadas de la implementación del engine

> **Status**: Accepted
> **Date**: 2026-05-28
> **Deciders**: @daniel, @marco

## Context

Medisage opera dos bots conversacionales (preventa y postventa) que atienden WhatsApp en el MVP, y debe poder extenderse a otros canales. La pregunta no es **si** habrá bots — es **dónde corren** los bots:

- **Opción in-process**: el backend FastAPI carga el LLM client (Anthropic SDK, OpenAI SDK, ...) y ejecuta turnos dentro del mismo proceso que sirve la API. Una sola codebase, deploy unificado.
- **Opción externa**: el bot vive en un servicio separado (puede ser otro FastAPI dedicado — el usuario mencionó `chatbot_sofia_v2` que ya está migrando — o una plataforma de bots como n8n, Vertex AI Agents, Dialogflow, o un servicio Node.js con LangChain). El backend medisage solo expone API para que el servicio externo lea/escriba.

El usuario respondió "aún no decidido, pero sería en este mismo backend FastAPI, o en otro backend FastAPI dedicado solo a eso". Es decir: **la decisión de dónde corre el motor es independiente del modelo de datos** que necesitamos para soportarlo.

Tenemos que decidir **cómo modelar el bot** de forma que **no atemos las entidades del módulo a una implementación específica** del engine. Esto importa porque:

1. **Cambiar el engine después** debe ser un cambio aditivo (nueva implementación), no una migración de tablas.
2. **Configurar bots distintos con providers distintos en paralelo** debe ser trivial (preventa con Claude embebido, postventa con webhook a `chatbot_sofia_v2`, por ejemplo).
3. **El frontend de admin** (ver estado del bot, depurar turnos) debe funcionar igual sin importar dónde corre el motor.
4. **Tool calling** debe funcionar en ambos casos. Las tools las ejecuta el backend medisage (porque tiene acceso a `scheduling`, `crm`, etc.), pero el LLM puede correr en cualquier lado.

Esta decisión afecta el ciclo de vida del proyecto durante años — el motor del bot va a cambiar muchas veces (otro modelo, otro provider, otra arquitectura). Las **entidades** del módulo deben sobrevivir todos esos cambios.

## Decision

**Las entidades del módulo `bots`** (`BotConfiguration`, `BotConfigurationVersion`, `ConversationBotState`, `BotTool`, `BotToolCall`, `BotEvent`) **son agnósticas al motor de ejecución**. Modelan **qué bot existe, con qué prompt, qué tools puede usar, qué pasó en cada turno** — sin imponer cómo se ejecuta el turno.

La **ejecución** vive en un paquete separado `app.modules.bots.services.engine` con:

- Una **interfaz abstracta** `BotEngine` que define:
  - `dispatch_turn(conversation, message, db)` — orquesta un turno.
  - `choose_bot_for_conversation(person, db)` — decide preventa/postventa.

- **Dos implementaciones intercambiables**:
  - `EmbeddedBotEngine` — corre el LLM in-process (Anthropic SDK, OpenAI SDK, etc.) según `BotConfigurationVersion.provider`.
  - `ExternalBotEngine` — POST al `BotConfigurationVersion.external_webhook_url` con HMAC; recibe callback en `/engine/external/callback`.

- La selección de qué engine usar se hace **en runtime, por bot**, leyendo `BotConfigurationVersion.provider`:
  - `provider IN {claude, openai, vertex_ai, azure_openai, langchain}` → `EmbeddedBotEngine`.
  - `provider = external_webhook` → `ExternalBotEngine`.

Las **tools** (`BotTool`) son ejecutadas siempre por el backend medisage, sin importar dónde viva el LLM. El registry `TOOL_REGISTRY` mapea `BotTool.code` a funciones Python en `app.modules.bots.services.engine.tools`. Cuando el LLM externo pide una tool, el `ExternalBotEngine` la ejecuta localmente y devuelve el resultado por el callback de tool_result.

## Alternatives Considered

### Opción A — Engine embebido fijo, una sola implementación

`bots.services.engine` carga Anthropic SDK directo. Las entidades incluyen `model_name`, `temperature`, etc. La opción "engine externo" no existe; si se quiere usar un servicio externo, se llama por HTTP desde dentro del engine embebido como herramienta — no como reemplazo.

- **Pros**:
  - Una sola codebase, deploy unificado.
  - Implementación más simple: una sola clase.
- **Cons**:
  - No soporta el caso "queremos que `chatbot_sofia_v2` siga corriendo y ser el cerebro de medisage". Tendríamos que migrar lógica que ya vive allá.
  - Atado al provider del SDK que esté en `pyproject.toml`. Cambiar de Anthropic a OpenAI implica cambios de código.
  - No permite que admin configure "este bot usa Claude, este otro usa OpenAI" sin meter más complejidad al engine.
- **Rechazada porque**: cierra la puerta a integraciones que ya existen en la organización (`chatbot_sofia_v2`) y a probar providers distintos sin tocar código.

### Opción B — Solo engine externo (medisage no ejecuta LLM)

Las entidades sirven solo para configurar el servicio externo. Medisage solo expone API y webhooks; el LLM siempre vive fuera.

- **Pros**:
  - Separación clara: medisage = datos + API; servicio externo = inteligencia.
  - Permite que el equipo del bot (si es distinto) trabaje con su propio stack.
- **Cons**:
  - **Dependencia operativa forzada**: para correr el bot localmente en dev, hay que tener el servicio externo arriba. Imposible "probar el bot en dev" sin operar el servicio externo.
  - **Latencia**: cada turno requiere round-trip HTTP + HMAC. Si el servicio externo está en otra región, suma 100-300ms.
  - Si el equipo no quiere mantener un servicio externo, el modelo no funciona.
- **Rechazada porque**: fuerza una dependencia operativa que no todos los equipos quieren asumir, y elimina la flexibilidad de "lo más simple primero, externalizar después si crece".

### Opción C — Tabla por implementación (`embedded_bot_config`, `external_bot_config`)

Una tabla por tipo de engine, con sus columnas específicas (provider, model_name vs webhook_url, secret). `Conversation.bot_config_type + bot_config_id` polimórfico.

- **Pros**:
  - Tipos fuertes por implementación.
- **Cons**:
  - **FKs polimórficas en `ConversationBotState`, `BotEvent`, `Message`** — el mismo anti-pattern que evitamos en ADR-004 con `ChannelAccount`.
  - Agregar un tercer engine (ej. WebSocket-based stream) obliga a otra tabla.
  - `ConversationBotState.bot_configuration_id` no podría apuntar a una tabla unificada — habría que duplicar el FK.
- **Rechazada porque**: repite el error de polimorfismo SQL que aprendimos a evitar en `conversations`.

### Opción D — Aceptada: `BotConfiguration(Version)` agnóstico + `BotEngine` interfaz con implementaciones

- Una sola tabla `BotConfiguration` + `BotConfigurationVersion` con columnas que cubren ambos casos:
  - Para embedded: `provider`, `model_name`, `parameters`.
  - Para external: `provider = 'external_webhook'`, `external_webhook_url`, `external_webhook_secret_name`.
- Una interfaz `BotEngine` con dos implementaciones. La selección de implementación es **lógica de runtime** (`engine_factory(version) → BotEngine`), no estructura de BD.
- Las tools, eventos, estado y tool calls son las mismas entidades en ambos casos.

## Consequences

### Positivas

- **Una clínica puede operar bots heterogéneos**: preventa embebido con Claude, postventa externo con `chatbot_sofia_v2`, en la misma instalación.
- **Migración entre engines es trivial**: editar `BotConfigurationVersion.provider` (creando una nueva versión) y promoverla con `/activate-version` — sin migración de schema.
- **Tests del modelo** no requieren motor real. Las entidades + repos se testean con `aiosqlite` (igual que el resto del template); el engine se mockea.
- **Frontend de admin** funciona idéntico — la columna "qué bot atiende" no necesita saber dónde corre.
- **Tool calling unificado**: las tools viven y se ejecutan en medisage. El engine externo solo orquesta el LLM.
- **Observabilidad común** (`BotEvent`): "cuánto cuesta el bot X esta semana" es el mismo query, sin importar dónde corre.

### Negativas / Trade-offs

- **Más boilerplate**: implementar la interfaz `BotEngine` + 2 concretas + factory es más código que una clase única. Aceptable: el costo se paga una vez, el beneficio se cosecha en cada cambio de provider futuro.
- **Las columnas `external_webhook_*` viven nullables** en `BotConfigurationVersion` y solo aplican cuando `provider='external_webhook'`. Validación en service (`if provider == 'external_webhook' then external_webhook_url required`). No es ideal estructuralmente, pero el alternativo (tablas separadas) es peor.
- **`TOOL_REGISTRY` debe sincronizarse manualmente con el catálogo en BD**: si admin crea una `BotTool` con `target_service = "scheduling.X.Y"` que no existe en el registry, el dispatcher debe fallar claro al primer invocación. **No** debe fallar al boot (admin podría estar configurando antes de implementar la tool). Lanzar `NotFoundException(code="TOOL_NOT_REGISTERED")` con mensaje explícito.
- **`ExternalBotEngine` introduce un protocolo HTTP+HMAC propio** entre medisage y el externo. Documentar ese protocolo (request schema, callback schema, tool_result flow) en `ADR-006` separado si se materializa ese caso (postergable hasta que tengamos un externo real).

### Lo que esto nos obliga a hacer

- **`bots.services.engine.__init__.py`**: exportar `engine_factory(version) → BotEngine`.
- **`bots.services.engine.embedded.py`**: implementar dispatch con clientes Python para providers comunes (Claude SDK como default). El switch entre providers va dentro del `EmbeddedBotEngine.__init__`.
- **`bots.services.engine.external.py`**: cliente HTTP + HMAC; endpoints de callback en routers del módulo (`/engine/external/callback`, `/engine/external/tool-result`).
- **`bots.services.engine.tools.__init__.py`**: `TOOL_REGISTRY: dict[str, Callable]` poblado con decorator `@register_tool("book_appointment")`.
- **`BotInvocationContext`** dataclass como contrato de los tool services. Documentar que las tools NO reciben `CurrentAuth` — reciben `BotInvocationContext` y son responsables de validar reglas de negocio sistémicas.
- **Tests obligatorios**:
  - `engine_factory` resuelve correctamente según `provider`.
  - `EmbeddedBotEngine` con mock del LLM: dispatch_turn persiste BotEvent + outbound Message.
  - `TOOL_REGISTRY` resuelve `target_service` existente; lanza error claro si no.
  - Tool con `requires_confirmation=true` y bot que invoca sin confirmar → debe rechazar en service.

## Referencias

- Ficha del módulo: [`docs/modules/bots.md`](../modules/bots.md)
- ADR relacionado: [ADR-004](ADR-004-conversation-channel-account.md) — `Conversation.bot_configuration_id` apunta a `BotConfiguration` agnóstica; cualquier engine la lee.
- Patrón futuro (postergado): si se materializa un engine externo en producción, documentar el protocolo HTTP+HMAC en ADR-006.
- Sobre tool calling como contrato: el `parameters_schema` debe ser JSON Schema compatible con [Anthropic Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) y [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling) — el subset común. Documentar la convención cuando se implementen las primeras tools.
