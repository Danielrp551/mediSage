# Módulo `bots` — UI design

> **Última actualización**: 2026-06-04 (diseño pre-implementación; reconciliado con el rediseño Firestore/CQRS [ADR-011], async por Cloud Tasks [ADR-012] y motor embebido multi-proveedor [ADR-005 actualizado]).
> **Audiencia**: developer implementando las pantallas de `bots` en `frontend/src/app/(main)/bots/`.
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). Spec autoritativa en `C:/tmp/bots_spec.md` (su §0 de reconciliaciones MANDA). Arquitectura del motor en [ADR-005](../../decisions/ADR-005-bot-engine-abstraction.md) (actualizado 2026-06-04); async del turno en [ADR-012](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md) (nuevo); el stream de mensajes que el bot lee vive en Firestore ([ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md)); forward-FK diferidas en [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md).

> **Alineación con crm/conversations/staff/clinic/catalog (módulos gold-standard ya en prod)**: `bots` reutiliza directamente los patrones shipped: DataTable + filtros con chip + deep-link (`OfficesClient`/`PersonsClient`), drawer de creación/edición (molde `VerticalsClient`/`LeadStatusDrawer`), tab dentro de un drawer/detalle (molde de las tabs Lead/Cliente de crm), `StatusBadge` (reuse de crm), `formatRelative` (helper **client-only** de `lib/utils/date.ts`, ya creado en crm), `ChannelIcon` (reuse de crm/conversations cuando se muestre el canal del hilo en la depuración), y el **editor M:N por multiselect** `SearchableOptionList` (el mismo de `StatusMatrixEditor` de crm). Las dos piezas bespoke de este módulo son (a) el **editor de versiones de prompt** (system_prompt grande + provider/model/params) dentro del tab Versiones, y (b) el **panel de Depuración por conversación** (read-only: estado del bot + timeline de `BotEvent` + `BotToolCall`), **análogo en peso (no en forma) al Timeline de Actividad de `crm`** y al inbox de `conversations`. Se documentan en detalle.

> **Contexto de diseño (binding por la spec)**: este es un módulo de **configuración + observabilidad de un motor conversacional** (admin-céntrico). Aplicar pensamiento de consolas de bots/LLM-ops modernas (Botpress, Voiceflow, OpenAI Playground/Assistants, Dialogflow CX, LangSmith/Langfuse para el trace) **ejecutado DENTRO de Fluent UI 9** del template. Consistencia con catalog/clinic/staff/crm/conversations shipped **>** introducir un estilo nuevo (regla de la metodología). Detalles técnicos no negociables:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Para otros colores usar tokens Fluent (`tokens.colorPaletteRedForeground1` para "turno fallido"/"error de tool", `tokens.colorPaletteGreenForeground1` para "turno completado"/"éxito", `tokens.colorNeutralForeground3` para eventos neutrales/sistema, `tokens.colorPaletteBlueForeground2` para "versión vigente", etc.) o un `color` derivado del provider/estado (badges).
> - Cualquier cálculo de la fecha de **"hoy"/"ayer"** que afecte el render (agrupación del timeline de eventos por día, "hace 2 min", separador "Hoy"/"Ayer") debe ser **client-only** — el SSR corre en UTC y desfasa el día en Lima (UTC-5). Lección recurrente de `staff`/`crm`/`conversations` (`new Date()` en SSR rompe el día y produce mismatch de hidratación).
> - **El motor del bot NO tiene UI de chat**: el browser **no** dispara turnos ni habla con el LLM. El turno lo corre el backend (encolado por Cloud Tasks, ADR-012) cuando entra un inbound en una conversación `assignee_type='bot'`. Toda la UI de `bots` es **configuración** (Configuraciones, Tools) u **observabilidad read-only** (Depuración). La única acción que dispara cómputo es el **"Disparar turno (debug)"** de admin (`POST /engine/dispatch-manual`, gated `BOT_ENGINE_INVOKE`), pensada para pruebas — y aun esa va server-side, no desde el browser al LLM.
> - **El secreto del proveedor NUNCA llega al front**: las API keys (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) son **globales por entorno** (Settings, vía `--set-secrets` de Cloud Run; spec §0.7). NO hay campo de API key por bot ni por versión en la UI. La UI elige `provider` + `model_name` + `parameters`; las credenciales las resuelve el backend. (El `external_webhook_secret_name` existe en el modelo pero su provider `external_webhook` está **diferido** — ver más abajo.)

---

## Glosario inglés → español del módulo (binding — UI 100 % en español)

> `key`, `code`, slugs, nombres de columna, enums, claves de `parameters`/JSON Schema y CSS classes se mantienen **en inglés** (identificadores de código). Solo los textos visibles van traducidos. Este glosario fija el vocabulario de TODA la UI de bots; no inventar sinónimos.

| Término (código / inglés) | Etiqueta visible (español) | Género / notas |
|---|---|---|
| Bot / BotConfiguration | **Bot** / **Configuración de bot** | masculino ("el bot", "este bot"); la entidad-config es femenina ("la configuración") |
| BotConfigurationVersion | **Versión** | femenino ("la versión", "esta versión") |
| current version | **Versión vigente** | la que el motor usa ahora |
| Activate version | **Activar versión** | verbo; botón "Activar" |
| BotType | **Tipo de bot** | masculino |
| `preventa` | **Preventa** | tipo de bot |
| `postventa` | **Postventa** | tipo de bot |
| `general` | **General** | tipo de bot |
| `custom` | **Personalizado** | tipo de bot |
| Provider / BotProvider | **Proveedor** | masculino ("el proveedor") |
| `openai` | **OpenAI** | proveedor (MVP, default) |
| `claude` | **Claude** (Anthropic) | proveedor (MVP) |
| `vertex_ai` / `azure_openai` / `external_webhook` | **Vertex AI** / **Azure OpenAI** / **Webhook externo** | proveedores (diferidos en MVP) |
| model / model_name | **Modelo** | masculino ("el modelo"); texto libre (ej. `gpt-4.1-mini`) |
| system_prompt | **Prompt de sistema** | masculino ("el prompt") |
| parameters | **Parámetros** | masculino plural; JSON (`temperature`, `max_tokens`, …) |
| BotTool / Tool | **Herramienta** | femenino ("la herramienta", "esta herramienta") |
| parameters_schema | **Esquema de parámetros** (JSON Schema) | masculino ("el esquema") |
| target_service | **Servicio destino** | masculino; `<module>.<service>.<function>` |
| requires_confirmation | **Requiere confirmación** | flag |
| tools del bot (M:N) | **Herramientas del bot** | el set de tools que puede usar |
| ConversationBotState | **Estado del bot** (en la conversación) | masculino ("el estado") |
| current_intent | **Intención** | femenino ("la intención") |
| collected_slots | **Datos capturados** (slots) | masculino plural |
| turn / turn_count | **Turno** / "N turnos" | masculino ("el turno") |
| BotEvent | **Evento** | masculino ("el evento") |
| `turn_started` | **Turno iniciado** | event_type |
| `turn_completed` | **Turno completado** | event_type |
| `turn_failed` | **Turno fallido** | event_type |
| `tool_dispatched` | **Herramienta invocada** | event_type |
| `handoff_triggered` | **Handoff disparado** | event_type (futuro) |
| BotToolCall | **Llamada a herramienta** | femenino ("la llamada") |
| `pending` (tool status) | **Pendiente** | estado de la llamada |
| `success` (tool status) | **Éxito** | estado de la llamada |
| `error` (tool status) | **Error** | estado de la llamada |
| `timeout` (tool status) | **Tiempo agotado** | estado de la llamada |
| tokens_in / tokens_out | **Tokens entrada** / **Tokens salida** | — |
| latency_ms | **Latencia** | femenino ("la latencia") |
| cost_estimated_usd | **Costo estimado** | masculino ("el costo"); USD |
| Dispatch (turn) | **Disparar turno** | verbo; debug |
| Reset state | **Reiniciar estado** | verbo; "Reiniciar el estado del bot" |
| Active / is_active | **Activo** / **Activa** | toggle de negocio (la herramienta/versión está habilitada) |
| Debugging / trace | **Depuración** / "Traza" | la pantalla de observabilidad |

> Decisión de género (igual criterio que crm/conversations): **Configuración / Versión / Herramienta / Intención / Llamada / Latencia** son **femeninos**; **Bot / Proveedor / Modelo / Prompt / Parámetro / Servicio / Turno / Evento / Esquema / Estado / Costo / Slot** son **masculinos**. Coherencia en confirms, empties y errores.

---

## Decisión de arquitectura: 2 CRUD de configuración (Configuraciones · Tools) + 1 panel de observabilidad (Depuración)

`clinic` estableció la regla, reafirmada por `staff`/`crm`/`conversations`: **si una entidad tiene sub-recursos con interacción propia (timelines, grids editables, máquinas de estado, versiones), su superficie es una página dedicada bespoke; si solo tiene metadata, va a drawer.** Aplicado a `bots`:

- **`BotConfiguration`** tiene un sub-recurso pesado: sus **versiones** (`BotConfigurationVersion`) — cada una con un `system_prompt` largo, `provider`/`model`/`parameters`, y una máquina de "vigencia" (`activate-version`). Eso justifica una superficie con **tab de Versiones** (un editor bespoke), pero la metadata del bot en sí (code/name/bot_type/description) es simple → el shell sigue siendo **DataTable + drawer**, con el tab de Versiones **dentro** del drawer/detalle del bot (molde de las tabs Lead/Cliente del detalle de `Person` en crm). NO se hace una página de detalle aparte: el bot tiene **una sola** superficie de sub-recurso (versiones), no varias densas — cabe en un drawer ancho con tabs (Datos · Versiones · Herramientas).
- **`BotTool`** es **catálogo de configuración** (admin): code/name/description/`parameters_schema`/`target_service`/`requires_confirmation` → **DataTable + drawer** (el drawer incluye un **editor JSON Schema** para `parameters_schema`). La **asignación M:N "herramientas del bot"** se edita con un **multiselect** (`SearchableOptionList`, molde `StatusMatrixEditor` de crm), embebido en el tab "Herramientas" del drawer del bot (no en la pantalla de Tools).
- **`ConversationBotState` + `BotEvent` + `BotToolCall`** son **observabilidad read-only por conversación** (traza del motor). No se crean/editan desde la UI (los escribe el motor). Su superficie es un **panel de Depuración** bespoke (estado + timeline de eventos + tool calls), **al que se entra desde el inbox de `conversations`** (un hilo `assignee_type='bot'` ofrece "Ver depuración del bot") **o desde la configuración del bot** (un acceso "Depurar una conversación"). Es el análogo del Timeline de crm / del hilo de conversations en peso.

| Recurso | Superficie | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **BotConfiguration** | `/bots/configuraciones` — DataTable, gated `BOT_CONFIGURATIONS_READ` | **drawer** (tab Datos) | **drawer con tabs** (Datos · Versiones · Herramientas) | molde `VerticalsClient` + tabs del detalle de crm |
| **BotConfigurationVersion** | sub-recurso → **tab "Versiones"** del drawer del bot | **sub-drawer/dialog "Nueva versión"** (editor de prompt + provider/model/params) | lista de versiones (read) + "Activar versión"; el prompt **NO se edita in-place** (cada cambio = versión nueva) | bespoke: editor de versiones |
| **BotTool** | `/bots/tools` — DataTable, gated `BOT_TOOLS_READ` | **drawer** (con editor JSON Schema) | **drawer** | molde `VerticalsClient`/`LeadStatusDrawer` |
| **bot_configuration_tool (M:N)** | sub-recurso → **tab "Herramientas"** del drawer del bot | — | **multiselect** `SearchableOptionList` → `PUT /configurations/{id}/tools` | molde `StatusMatrixEditor` de crm |
| **ConversationBotState** | **panel de Depuración** (`/bots/depuracion?conv=<id>`), read-only | — (lo crea el motor) | read + "Reiniciar estado" (gated `BOT_STATE_WRITE`) | bespoke: panel de observabilidad |
| **BotEvent** | dentro de Depuración — **timeline por turno** | — (lo escribe el motor) | read-only (audit inmutable, sin SD) | molde Timeline de crm (feed por día) |
| **BotToolCall** | dentro de Depuración — bajo cada turno/evento | — (lo escribe el motor) | read-only (audit inmutable, sin SD) | tarjetas anidadas (args/result/status) |

### Por qué Versiones es un tab del drawer y no una página aparte

| Opción | Veredicto |
|---|---|
| **A. Drawer ancho con tabs (Datos · Versiones · Herramientas)** — el bot es la entidad raíz; sus versiones y sus tools son sub-recursos que el admin gestiona en el contexto del mismo bot, sin perder de vista cuál está editando. El tab Versiones muestra la lista + un sub-dialog "Nueva versión" para el editor pesado de prompt. | **Elegida** |
| B. Página de detalle `/bots/configuraciones/{id}` (molde `PersonDetailShell`) con tabs | Rechazada para el MVP — el bot solo tiene **un** sub-recurso pesado (versiones) + uno liviano (tools M:N); no justifica una página-detalle completa como `Person` (que tiene Lead/Cliente/Timeline). Un `Drawer size="large"` con 3 tabs es suficiente y consistente con catalog/clinic. (Si en una fase futura el bot gana más superficies densas —analytics, A/B de versiones— se promueve a página-detalle sin romper el contrato.) |
| C. Editor de prompt inline en la fila de la DataTable | Rechazada — el `system_prompt` es un textarea grande (cientos de líneas) + provider/model/params; no cabe en una fila. |

### Por qué Depuración es read-only y bespoke

La traza del motor (`BotEvent` + `BotToolCall`) es **audit inmutable** (sin SoftDelete, spec §2) — no se edita. Es un **feed cronológico por turno** con métricas (tokens/latencia/costo) y, anidadas, las llamadas a herramientas (args/result/status). Esto es exactamente el espíritu del **Timeline de crm** (feed por día, client-only, tarjetas tipadas, `React.memo` + `content-visibility`) — se **reusa ese espíritu**, no se introduce librería externa de trace. La única mutación del panel es **"Reiniciar estado"** (`POST /conversations/{cid}/state/reset`, gated `BOT_STATE_WRITE`) y el **"Disparar turno (debug)"** (`POST /engine/dispatch-manual`, gated `BOT_ENGINE_INVOKE`) — ambos server-side.

---

## Sidebar — extensión de `NAV_ITEMS` (grupo "Bots", gated `MENU-BOTS`)

> ⚠ **Textos UI en español**. `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un parent item `bots` con 3 children, entre `conversations` y `admin`:

```ts
{
  key: "bots",
  label: "Bots",
  icon: "BotRegular",                          // verificar en la versión de Fluent; fallback "BrainCircuitRegular" / "SparkleRegular"
  children: [
    { key: "configuraciones", label: "Configuraciones", icon: "BotRegular",        url: "/bots/configuraciones", permissions: ["BOT_CONFIGURATIONS_READ"] },
    { key: "tools",           label: "Herramientas",     icon: "WrenchRegular",     url: "/bots/tools",           permissions: ["BOT_TOOLS_READ"] },
    { key: "depuracion",      label: "Depuración",       icon: "BugRegular",        url: "/bots/depuracion",      permissions: ["BOT_EVENTS_READ"] },
  ],
},
```

> El parent usa `MENU-BOTS` como gate de visibilidad del grupo. Cada child gatea por **su** permiso de lectura. Un **ASESOR** tiene los permisos read-only del módulo (`BOT_CONFIGURATIONS_READ`, `BOT_STATE_READ`, `BOT_EVENTS_READ`, `BOT_TOOL_CALLS_READ` — spec §5), por lo que ve **Configuraciones** (read) y **Depuración**, pero **NO Herramientas** (no tiene `BOT_TOOLS_READ` — el catálogo de tools es solo del ADMIN). El **DOCTOR** no tiene ningún permiso de bots → no ve el grupo. Los permisos de escritura (`BOT_CONFIGURATIONS_CREATE/UPDATE/DELETE`, `BOT_CONFIGURATION_VERSIONS_WRITE`, `BOT_TOOLS_WRITE`, `BOT_STATE_WRITE`, `BOT_ENGINE_INVOKE`) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>` / `usePermissions()`.

> Iconos Fluent (verificar que existan en la versión instalada; usar fallback si no): `BotRegular`/`BrainCircuitRegular`/`SparkleRegular` (grupo + Configuraciones), `WrenchRegular`/`ToolboxRegular` (Herramientas), `BugRegular`/`DocumentSearchRegular` (Depuración). Mismo criterio de verificación que `crm` con `PeopleRegular`, `staff` con `DoctorRegular` y `conversations` con `ChatRegular`.

> **Acceso a Depuración desde conversations**: además del item de nav (que abre la pantalla sin `?conv=`, mostrando el selector de conversación), el panel se entra **contextualmente** desde el inbox de `conversations`: el header del hilo de una conversación `assignee_type='bot'` muestra un botón/menú **"Ver depuración del bot"** (gated `BOT_EVENTS_READ`) → `/bots/depuracion?conv=<id>`. Es el camino natural del asesor/admin que ve un hilo atendido por bot y quiere entender qué decidió el motor.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error / sin permiso) + tabla de componentes Fluent.

1. **`/bots/configuraciones`** — CRUD de `BotConfiguration` (DataTable + drawer con tabs **Datos · Versiones · Herramientas**; el tab Versiones es el editor bespoke de prompt/provider/model/params + "Activar versión").
2. **`/bots/tools`** — CRUD de `BotTool` (DataTable + drawer con **editor JSON Schema** para `parameters_schema`).
3. **`/bots/depuracion`** — panel de observabilidad read-only por conversación (estado del bot + timeline de `BotEvent` + `BotToolCall`).

---

### Pantalla 1 — `/bots/configuraciones` (CRUD de BotConfiguration + tab Versiones + tab Herramientas)

Lista (DataTable, molde `VerticalsClient` de catalog) de las configuraciones de bot de la clínica + drawer con tabs. Gated `BOT_CONFIGURATIONS_READ`. El **ASESOR** ve la lista y el drawer en **modo read** (sin botones de mutación). El **ADMIN** crea/edita/elimina y gestiona versiones y herramientas.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Configuraciones de bot                                                       │
│   Define los bots que atienden automáticamente tus conversaciones.             │
│                                                          [ + Nuevo bot ]        │
│   ╭─ DataTable ──────────────────────────────────────────────────────────────╮│
│   │ ⋯ │ Código          │ Nombre           │ Tipo      │ Versión vig.│ Estado ││
│   ├───┼─────────────────┼──────────────────┼───────────┼─────────────┼────────┤│
│   │ ⋯ │ preventa        │ Bot de Preventa  │ Preventa  │ v3 ·OpenAI  │ Activo ││
│   │ ⋯ │ postventa_dental│ Postventa Dental │ Postventa │ v1 ·Claude  │ Activo ││
│   │ ⋯ │ general_info    │ Info General     │ General   │ — sin ver.  │ Inactivo││
│   ╰──────────────────────────────────────────────────────────────────────────╯│
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (`key` en inglés, header en español) — mapean a `BotConfigurationItem`:

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `actions` | `""` | RowActions | — | menú `…` con Ver/Editar/Eliminar (gated) |
| `code` | Código | text (mono) | ✅ (server) | `BotConfiguration.code` (slug) |
| `name` | Nombre | text | ✅ (server) | `BotConfiguration.name` |
| `bot_type` | Tipo | badge | ❌ (deep-link/filtro) | `<Badge>` "Preventa"/"Postventa"/"General"/"Personalizado" (color por tipo) |
| `current_version` | Versión vigente | badge compuesto | ❌ (derivado) | "v{version} · {Proveedor}" o "— sin versión" (neutral) si `current_version_id` NULL |
| `active` | Estado | badge | ❌ | "Activo"/"Inactivo" (`ActiveMixin`) — reuse `StatusBadge` de crm |

> `ALLOWED_FIELDS` del repo: `code`, `name`, `bot_type`, `active`, `created_on` (solo columnas reales — lección hotfix `cd10c78` de staff). `current_version` es **derivado** (se hidrata por batch map: `current_version_id` → `{version, provider}` de `bot_configuration_version`) → **NO** sortable/filterable por su texto. **`defaultSort = created_on desc`** (spec §6; el prefetch del RSC y el `defaultSort` de la lista DEBEN coincidir — lección desync footer de crm). Filtro opcional por `bot_type` (deep-link `?bot_type=preventa`, columna real).

**RowActions** (gated por `usePermissions()`):
- 👁 **Ver** — `BOT_CONFIGURATIONS_READ`. Abre el drawer en modo read (tabs read-only).
- ✏ **Editar** — `BOT_CONFIGURATIONS_UPDATE`. Abre el drawer en modo edit.
- 🗑 **Eliminar** — `BOT_CONFIGURATIONS_DELETE`. Confirm dialog (soft-delete).

**Botón "+ Nuevo bot"**: gated `<PermissionGuard anyOf={["BOT_CONFIGURATIONS_CREATE"]}>`. Abre `BotConfigurationDrawer` en create (solo el tab Datos hasta que el bot exista; Versiones/Herramientas se habilitan tras crear).

#### Drawer con tabs — `BotConfigurationDrawer` (`<Drawer size="large">`)

El drawer tiene un `<TabList>` arriba con 3 tabs. En **create** solo el tab **Datos** está disponible (no hay bot al que colgarle versiones/tools todavía); tras guardar, el drawer permanece abierto en modo edit y habilita los otros dos tabs.

```
                  ┌───────────────────────────────────────────────────────┐
                  │  Bot de Preventa                                   ✕   │
                  │  [ Datos ] [ Versiones ] [ Herramientas ]             │
                  ├───────────────────────────────────────────────────────┤
                  │  (Tab Datos)                                          │
                  │  Código *                                             │
                  │  [ preventa                                         ] │
                  │  Nombre *                                             │
                  │  [ Bot de Preventa                                 ] │
                  │  Tipo de bot *                                        │
                  │  [ Preventa                                       ▾] │
                  │  Descripción                                          │
                  │  [ ……………………………………………………………………………………………………… ]      │
                  │  Máx. turnos por conversación  (opcional)             │
                  │  [ 20 ]   ⓘ Vacío = sin límite.                       │
                  │  ───────────────────────────────────────────────────  │
                  │  Versión vigente: v3 · OpenAI (gpt-4.1-mini)         │
                  │  ⓘ El prompt y los parámetros se editan creando una  │
                  │     nueva versión (pestaña Versiones).               │
                  │  ☑ Activo                                            │
                  ├───────────────────────────────────────────────────────┤
                  │                          [ Cancelar ] [ Guardar ]    │
                  └───────────────────────────────────────────────────────┘
```

**Tab Datos — campos y validación (Zod, `botConfigurationSchema`)** — espejo de `BotConfigurationCreate/Update` (ver [`backend.md`](./backend.md) y la spec §2):
- `code` requerido (1–40; slug `^[a-z0-9_]+$`; el front sugiere minúsculas/guion-bajo). **Conflicto 409 `BOT_CONFIGURATION_CODE_TAKEN`** → error inline: "Ya existe un bot con este código."
- `name` requerido (1–120).
- `bot_type` requerido (`<Dropdown>` de `BotType`: Preventa/Postventa/General/Personalizado).
- `description` opcional (textarea).
- `max_turns_per_conversation` opcional (int ≥ 1; vacío = NULL = sin límite). Hint: "Vacío = sin límite. Guard opcional para evitar bucles largos."
- `active` (`<Switch>`).
- **`current_version_id` NO es editable directamente** en el tab Datos — se muestra read-only ("Versión vigente: v3 · OpenAI") + el aviso de que se cambia desde el tab Versiones (botón "Activar"). Un bot **sin versión vigente** (`current_version_id` NULL) muestra "— sin versión (no usable)" en rojo suave + hint "Crea y activa una versión para que el bot pueda responder."

**Tab Versiones** (el editor bespoke — pieza pesada de esta pantalla):

```
                  ┌───────────────────────────────────────────────────────┐
                  │  Bot de Preventa                                   ✕   │
                  │  [ Datos ] [ Versiones ] [ Herramientas ]             │
                  ├───────────────────────────────────────────────────────┤
                  │  Versiones                          [ + Nueva versión ]│
                  │  ┌───────────────────────────────────────────────────┐│
                  │  │ ● v3   OpenAI · gpt-4.1-mini      VIGENTE   👁     ││
                  │  │   "Eres el asistente de preventa…"  · hace 2 días ││
                  │  ├───────────────────────────────────────────────────┤│
                  │  │ ○ v2   OpenAI · gpt-4.1-mini      Activa  👁[Activar]│
                  │  │   "Eres un asistente comercial…"   · hace 1 sem.  ││
                  │  ├───────────────────────────────────────────────────┤│
                  │  │ ○ v1   Claude · claude-3-5-sonnet Inactiva 👁      ││
                  │  │   "Prompt inicial"   (desactivada)  · hace 1 mes  ││
                  │  └───────────────────────────────────────────────────┘│
                  └───────────────────────────────────────────────────────┘
```

- Lista de `BotConfigurationVersionItem` ordenada por `version desc` (la más nueva arriba). Cada fila: punto/badge **VIGENTE** (`●`, `tokens.colorPaletteBlueForeground2`) si `id == current_version_id`; badge **Activa/Inactiva** (`is_active`, distinto de vigente — una versión puede estar activa pero no ser la vigente); `version` (v3, v2…); badge de **Proveedor** + **modelo** (`OpenAI · gpt-4.1-mini`); un preview de 1 línea del `system_prompt` (truncado); `formatRelative(created_on)` (**client-only**); ícono 👁 **Ver versión** (abre el sub-dialog en modo read con el prompt completo) y, si NO es la vigente y `is_active`, botón **"Activar"** (gated `BOT_CONFIGURATION_VERSIONS_WRITE`).
- **"Activar versión"** → `POST /configurations/{id}/activate-version/{vid}` → setea `current_version_id`. Confirm sutil (no destructivo): "¿Activar la versión v{n}? Las conversaciones nuevas usarán este prompt." (las conversaciones **en curso** mantienen la versión con la que arrancaron — `ConversationBotState.bot_configuration_version_id` NO se migra; spec §2). Tras activar: refetch de la lista de versiones + de la fila del bot (la columna "Versión vigente" cambia) + `router.refresh()`.
- **Botón "+ Nueva versión"** (gated `BOT_CONFIGURATION_VERSIONS_WRITE`) → abre el **sub-dialog/sub-drawer de versión** (`BotVersionDrawer`):

```
        ┌─────────────────────────────────────────────────────────────────┐
        │  Nueva versión — Bot de Preventa                            ✕   │
        ├─────────────────────────────────────────────────────────────────┤
        │  Proveedor *                    Modelo *                         │
        │  [ OpenAI                    ▾] [ gpt-4.1-mini                 ] │
        │  Prompt de sistema *                                             │
        │  ┌─────────────────────────────────────────────────────────────┐│
        │  │ Eres el asistente de preventa de la clínica.                ││
        │  │ Tu objetivo es responder consultas sobre servicios y        ││
        │  │ precios, y registrar el interés del contacto como lead.     ││
        │  │ …                                                           ││
        │  │                                              (autosize, 8-30)││
        │  └─────────────────────────────────────────────────────────────┘│
        │  Parámetros (JSON)                                               │
        │  ┌─────────────────────────────────────────────────────────────┐│
        │  │ { "temperature": 0.4, "max_tokens": 800 }                   ││
        │  └─────────────────────────────────────────────────────────────┘│
        │  ⓘ Esquema libre por proveedor. Vacío = {}.                     │
        │  Notas (changelog, opcional)                                     │
        │  [ Ajusté el tono y agregué el cierre de lead.                ] │
        │  ─────────────────────────────────────────────────────────────  │
        │  ☐ Activar esta versión al crearla                              │
        ├─────────────────────────────────────────────────────────────────┤
        │                              [ Cancelar ] [ Crear versión ]     │
        └─────────────────────────────────────────────────────────────────┘
```

**Campos y validación del sub-dialog (Zod, `botVersionSchema`)** — espejo de `BotConfigurationVersionCreate` (ver [`backend.md`](./backend.md), spec §2):
- `provider` requerido (`<Dropdown>` de `BotProvider`). **MVP: solo `openai` (default) y `claude` habilitados**; `vertex_ai`/`azure_openai`/`external_webhook` se listan **deshabilitados** con sufijo "(próximamente)" para dejar claro el roadmap (un provider sin adaptador da `PROVIDER_NOT_SUPPORTED` 400 en runtime). Al elegir un provider, el placeholder de `model_name` sugiere el default de ese provider.
- `model_name` requerido (1–120; texto libre). Default sugerido **`gpt-4.1-mini`** (OpenAI). Hint: "Depende del proveedor. Ej.: `gpt-4.1-mini`, `claude-3-5-sonnet-latest`."
- `system_prompt` requerido (textarea grande autosize 8–30 líneas; el campo pesado). Sin límite duro de UI (es `text`).
- `parameters` opcional — **editor JSON** (`<Textarea>` mono con validación client-side: debe parsear a objeto; vacío = `{}`). Hint: "Esquema libre por proveedor (`temperature`, `max_tokens`, `top_p`…)." Error inline si el JSON no parsea: "Parámetros: JSON inválido."
- `notes` opcional (changelog del prompt).
- **Provider `external_webhook` (DIFERIDO)**: si se eligiera (deshabilitado en MVP), aparecerían `external_webhook_url` (requerido → si no, `EXTERNAL_WEBHOOK_URL_REQUIRED` 400) y `external_webhook_secret_name`. **En el MVP estos campos NO se renderizan** (el provider está deshabilitado en el dropdown). Se documentan para la fase F4.
- Checkbox **"Activar esta versión al crearla"** (opcional): si marcado, el front, tras `POST /configurations/{id}/versions`, encadena `POST /configurations/{id}/activate-version/{nuevo_vid}`. Por defecto desmarcado (crear ≠ activar — promoción explícita).

> **El prompt NO se edita in-place** (binding spec §2): editar el `system_prompt`/`parameters`/`provider`/`model` de una versión existente **no existe** como operación — cada cambio es una **versión nueva** (`POST /versions`), preservando el historial/changelog. El sub-dialog en modo **read** (👁) muestra la versión completa con todos los campos deshabilitados + un botón "Crear nueva a partir de esta" (pre-rellena el form de nueva versión con los valores de la versión vista — atajo, no edición). La promoción se hace con "Activar".

**Tab Herramientas** (editor M:N — molde `StatusMatrixEditor` de crm):

```
                  ┌───────────────────────────────────────────────────────┐
                  │  Bot de Preventa                                   ✕   │
                  │  [ Datos ] [ Versiones ] [ Herramientas ]             │
                  ├───────────────────────────────────────────────────────┤
                  │  Herramientas que este bot puede usar                  │
                  │  ┌───────────────────────────────────────────────────┐│
                  │  │ 🔍 Buscar herramientas…                           ││
                  │  │ ☑ list_verticals          Listar verticales       ││
                  │  │ ☑ list_services_by_vert.  Listar servicios        ││
                  │  │ ☑ register_lead_note      Registrar nota de lead  ││
                  │  │ ☑ set_lead_status     ⚠   Cambiar estado de lead  ││
                  │  │ ☑ resolve_or_create_co.   Resolver/crear contacto ││
                  │  │ ☐ list_products_by_vert.  Listar productos        ││
                  │  └───────────────────────────────────────────────────┘│
                  │  El bot solo podrá invocar las herramientas marcadas.  │
                  │  ⚠ = requiere confirmación.                           │
                  ├───────────────────────────────────────────────────────┤
                  │                          [ Cancelar ] [ Guardar ]    │
                  └───────────────────────────────────────────────────────┘
```

- **Multiselect** (`SearchableOptionList`, **reuse** del helper de admin/users — el mismo que `StatusMatrixEditor`) con las herramientas **activas** del catálogo (`GET /tools/list?active=true` o el `bot_tool` activo). Cada opción: `code` (mono) + `name` (ES) + un `⚠` si `requires_confirmation`. La búsqueda filtra por `code`/`name`.
- Estado inicial = las tools ya asignadas al bot (`GET /configurations/{id}/tools`). Al guardar: `PUT /configurations/{id}/tools { tool_ids: [...] }` (**reemplaza** el set M:N completo — bulk, molde crm `PUT /transitions`). Tras guardar: toast "Herramientas actualizadas".
- Gated `BOT_CONFIGURATIONS_UPDATE` (la asignación M:N es una edición del bot). Si el viewer es read-only, el multiselect se renderiza deshabilitado (solo ver qué tools tiene).
- **Empty del catálogo de tools**: si no hay tools (catálogo vacío), el tab muestra "Aún no hay herramientas. Crea herramientas en la sección Herramientas para asignarlas a este bot." + link a `/bots/tools` (gated `BOT_TOOLS_READ`).

**Modo del drawer**: `create` / `edit` / `read`. Títulos: el `name` del bot (o "Nuevo bot" en create). Footer del tab Datos: `[ Cancelar ] [ Crear / Guardar ]` (`Creando…`/`Guardando…` en pending); en `read` solo `[ Cerrar ]`. Los tabs Versiones/Herramientas tienen sus propias acciones (Activar / Guardar herramientas) — no comparten el footer del tab Datos.

#### Estados (Pantalla 1)

- **Empty (sin bots)**:
```
┌────────────────────────────────────────────────────────────────────┐
│                       🤖  (BotRegular)                               │
│                       Aún no hay bots                                │
│      Crea un bot para que atienda automáticamente las               │
│      conversaciones entrantes de tus canales.                       │
│                         [ + Nuevo bot ]                             │
└────────────────────────────────────────────────────────────────────┘
```
- **Loading (primera carga)**: DataTable con 5 skeleton rows.
- **No-results (filtro por tipo sin matches)**: "No hay bots con los filtros actuales."
- **Refetching (background)**: tabla `opacity: 0.55` + spinner top-right (igual que catalog/clinic — aquí es CRUD manual, no polling).
- **Guardando (drawer)**: footer disabled (`useTransition`); fields disabled.
- **Versiones — empty**: "Este bot no tiene versiones todavía. Crea la primera versión con su prompt para poder activarla." + botón "+ Nueva versión". (Un bot sin versión vigente no puede responder — el badge "— sin versión (no usable)" lo refleja en Datos y en la fila de la lista.)
- **Activar versión sin versión activa (`is_active=false`)**: el botón "Activar" NO aparece en versiones inactivas (una versión desactivada no puede ser vigente). Si por carrera se intentara, el backend valida.
- **Error 409 (`BOT_CONFIGURATION_CODE_TAKEN`)**: `<MessageBar intent="error">` arriba del tab Datos + error inline en `code`: "Ya existe un bot con este código."
- **Error 400 (`EXTERNAL_WEBHOOK_URL_REQUIRED`)**: no ocurre en MVP (provider externo deshabilitado); documentado para F4.
- **Error 400 (`BOT_VERSION_NOT_OWNED` / `NO_CURRENT_VERSION`)**: defensa en profundidad del backend (activar una versión de otro bot / activar sin versión) — `<MessageBar intent="error">` con copy "No se pudo activar la versión." + log. No debería ocurrir desde la UI (solo se listan versiones del propio bot).
- **Error de red**: `<MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.
- **Eliminar bot**: `<ConfirmDialog destructive>` — "¿Eliminar el bot '{nombre}'? Las conversaciones que esté atendiendo dejarán de recibir respuestas automáticas. La traza de eventos se conserva." (soft-delete; los `BotEvent`/`BotToolCall` quedan como audit). Si negocio quiere que un bot deje de operar sin borrar, usar el toggle **Activo** (disable, no delete — `ActiveMixin`).
- **Sin permiso de escritura (ASESOR)**: la lista y el drawer se ven en **modo read** (sin "+ Nuevo bot", sin Editar/Eliminar/Activar/Guardar; los tabs muestran datos read-only).

#### Componentes Fluent UI (Configuraciones)

| Concepto UI | Componente |
|---|---|
| Lista | `<DataTable<BotConfigurationItem>>` + `useTableQuery({ queryKey: "bots:configurations" })` |
| Filtro tipo de bot | `<Dropdown>` + `nuqs useQueryState("bot_type")` (opcional; deep-link + chip) |
| Badge tipo | `<Badge appearance="tint" color={byType}>` "Preventa"/"Postventa"/"General"/"Personalizado" |
| Badge versión vigente | `<Badge>` "v{n} · {Proveedor}" / "— sin versión" (neutral) |
| Badge estado | `<StatusBadge>` "Activo"/"Inactivo" (**reuse** de crm) |
| Drawer con tabs | `<Drawer size="large">` + `<TabList>` (Datos · Versiones · Herramientas) |
| Campos Datos | `<FormField>` + `<Input>` / `<Dropdown>` / `<Textarea>` / `<Switch>` vía `Controller` (react-hook-form) |
| Lista de versiones | `BotVersionList` (custom) — filas con badge vigente/activa + `BotProviderBadge` + preview + `formatRelative` + acciones |
| Badge proveedor | `BotProviderBadge` (custom) — "OpenAI"/"Claude"/… + color por provider |
| Sub-dialog versión | `<Dialog>`/`<Drawer size="medium">` `BotVersionDrawer` (editor prompt + provider/model/params/notes) |
| Editor prompt | `<Textarea>` autosize (8–30 líneas) |
| Editor parámetros JSON | `<Textarea>` mono + validación parse client-side |
| Activar versión | `<Button appearance="subtle">` "Activar" + `<ConfirmDialog>` (no destructivo) |
| Editor M:N herramientas | `SearchableOptionList` (**reuse**, molde `StatusMatrixEditor`) → `PUT /configurations/{id}/tools` |
| Row menu | `<RowActions item={c} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive />` |
| Empty / error | `<EmptyState>` + `<MessageBar intent="error">` |

---

### Pantalla 2 — `/bots/tools` (CRUD de BotTool — admin)

Lista (DataTable, molde `VerticalsClient`) del catálogo de herramientas + drawer create/edit con **editor JSON Schema** para `parameters_schema`. Gated `BOT_TOOLS_READ` (admin; el ASESOR no ve este item). La asignación M:N "herramientas del bot" **no vive aquí** — vive en el tab Herramientas del drawer del bot (Pantalla 1).

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│   Herramientas                                                                     │
│   Acciones que un bot puede invocar durante una conversación.                      │
│                                                          [ + Nueva herramienta ]   │
│   ╭─ DataTable ──────────────────────────────────────────────────────────────────╮│
│   │ ⋯ │ Código                │ Nombre              │ Servicio destino       │Conf.│Est.│
│   ├───┼───────────────────────┼─────────────────────┼────────────────────────┼─────┼───┤│
│   │ ⋯ │ list_verticals        │ Listar verticales   │ catalog.vertical.list… │  —  │Act││
│   │ ⋯ │ set_lead_status       │ Cambiar estado lead │ crm.person_lead_statu… │ ⚠ Sí│Act││
│   │ ⋯ │ resolve_or_create_co. │ Resolver/crear cont.│ crm.person.find_by_id… │  —  │Act││
│   │ ⋯ │ book_appointment      │ Agendar cita        │ scheduling.appointment…│ ⚠ Sí│Inac││ ← diseñada, no registrada
│   ╰──────────────────────────────────────────────────────────────────────────────╯│
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (`key` en inglés, header en español) — mapean a `BotToolItem`:

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `actions` | `""` | RowActions | — | menú `…` con Ver/Editar/Eliminar (gated) |
| `code` | Código | text (mono) | ✅ (server) | `BotTool.code` |
| `name` | Nombre | text | ✅ (server) | `BotTool.name` |
| `target_service` | Servicio destino | text (mono, truncado + tooltip) | ✅ (server) | `target_service` (`<module>.<service>.<function>`) |
| `requires_confirmation` | Confirmación | badge | ❌ | "⚠ Sí" (warning) / "—" (neutral) |
| `active` | Estado | badge | ❌ | "Activo"/"Inactivo" (reuse `StatusBadge`) |

> `ALLOWED_FIELDS` del repo: `code`, `name`, `target_service`, `active`, `created_on`. `requires_confirmation` es booleano → puede filtrarse como flag (opcional), pero no se sortea por texto. **`defaultSort = code asc`** (o `created_on desc`). Una herramienta cuyo `target_service` no está en el `TOOL_REGISTRY` (ej. las diferidas `book_appointment` → `scheduling.*`) **se puede listar igual** — el `TOOL_NOT_REGISTERED` (404) solo ocurre **en runtime** cuando el motor intenta invocarla, no en el catálogo (spec §2). La UI puede mostrar un sutil indicador "no registrada" si el backend expone `is_registered` en el item (opcional — ver más abajo).

> **Indicador "no registrada" (opcional, recomendado)**: el `BotToolItem` puede incluir un flag derivado `is_registered` (`target_service in TOOL_REGISTRY`, calculado server-side). Si `false`, la fila muestra un `<Badge color="warning">` "No registrada" con tooltip "El servicio destino no está disponible en este entorno; invocarla dará error." Esto hace visible el caso de las tools **diseñadas pero no seedeadas** (`book_appointment`/`check_availability` → `scheduling.*` inexistente; spec §0.4) sin romper el catálogo.

**RowActions** (gated `usePermissions()`, todas requieren `BOT_TOOLS_WRITE` salvo Ver):
- 👁 **Ver** — `BOT_TOOLS_READ`. Drawer en modo read.
- ✏ **Editar** — `BOT_TOOLS_WRITE`. Drawer en modo edit.
- 🗑 **Eliminar** — `BOT_TOOLS_WRITE`. Confirm dialog (soft-delete).

**Botón "+ Nueva herramienta"**: gated `<PermissionGuard anyOf={["BOT_TOOLS_WRITE"]}>`.

#### Drawer create/edit — `BotToolDrawer` (`<Drawer size="medium">`)

```
                  ┌─────────────────────────────────────────────────────┐
                  │  Nueva herramienta                              ✕   │
                  ├─────────────────────────────────────────────────────┤
                  │  Código *                                           │
                  │  [ list_services_by_vertical                      ] │
                  │  Nombre *                                           │
                  │  [ Listar servicios por vertical                  ] │
                  │  Descripción *  (la lee el modelo para decidir)     │
                  │  [ Devuelve los servicios activos de una vertical  │
                  │    dada. Úsala cuando el contacto pregunte qué…  ] │
                  │  Esquema de parámetros (JSON Schema) *              │
                  │  ┌─────────────────────────────────────────────────┐│
                  │  │ {                                               ││
                  │  │   "type": "object",                             ││
                  │  │   "properties": {                               ││
                  │  │     "vertical_id": { "type": "string" }         ││
                  │  │   },                                            ││
                  │  │   "required": ["vertical_id"]                   ││
                  │  │ }                                               ││
                  │  └─────────────────────────────────────────────────┘│
                  │  ⓘ Subset común OpenAI/Anthropic. Debe ser un       │
                  │     objeto JSON Schema válido.                      │
                  │  Servicio destino *                                 │
                  │  [ catalog.service.list_by_vertical               ] │
                  │  ⓘ <módulo>.<servicio>.<función> resuelto por el    │
                  │     registro de herramientas.                      │
                  │  ☐ Requiere confirmación                            │
                  │  ☑ Activa                                           │
                  ├─────────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Crear ]      │
                  └─────────────────────────────────────────────────────┘
```

**Campos y validación (Zod, `botToolSchema`)** — espejo de `BotToolCreate/Update` (ver [`backend.md`](./backend.md), spec §2):
- `code` requerido (1–60; slug `^[a-z0-9_]+$`). **Conflicto 409 `BOT_TOOL_CODE_TAKEN`** → error inline: "Ya existe una herramienta con este código."
- `name` requerido (1–120).
- `description` requerido (textarea) — **importante**: hint "La lee el modelo para decidir cuándo invocar esta herramienta. Sé claro y específico." (la calidad de esta descripción afecta el comportamiento del LLM — vale destacarlo).
- **`parameters_schema`** requerido — **editor JSON Schema** (`<Textarea>` mono / editor con resaltado si está disponible, autosize). Validación client-side: debe parsear a un **objeto** JSON (idealmente con `type: "object"` en la raíz — warning suave si no). Hint: "Subset común OpenAI/Anthropic (JSON Schema). Define los argumentos que el bot debe pasar." Error inline si no parsea: "Esquema de parámetros: JSON inválido." Vacío no permitido (al menos `{"type":"object","properties":{}}`).
- **`target_service`** requerido (1–120; `<module>.<service>.<function>`). Hint: "Identifica la función del backend que ejecuta la herramienta (resuelta por el registro). Ej.: `crm.person_lead_status.transition`." (NO se valida contra el registry en el form — el `TOOL_NOT_REGISTERED` es runtime; opcionalmente, si el item trae `is_registered`, el front puede advertir "Este servicio no está registrado en este entorno" como warning no bloqueante).
- `requires_confirmation` (`<Switch>`) — hint: "Si está activo, las acciones de esta herramienta requerirán confirmación antes de ejecutarse." (en MVP gobierna la marca `⚠`; el flujo de confirmación humana en banda es futuro — hoy aplica a tools sensibles como `set_lead_status`).
- `active` (`<Switch>`).

**Modo del drawer**: `create` / `edit` / `read`. Títulos: "Nueva herramienta" / "Editar herramienta" / "Herramienta" (read). Footer: `[ Cancelar ] [ Crear / Guardar ]`; en `read` solo `[ Cerrar ]`.

> **HONESTIDAD (binding spec §0.4)**: este catálogo permite crear herramientas cuyo `target_service` apunta a un módulo aún inexistente (ej. `scheduling.*`). Eso es **deliberado** — deja el roadmap visible — pero esas tools darán `TOOL_NOT_REGISTERED` (404 runtime) si un bot las invoca. El MVP **seedéa** solo las 5 tools de crm/catalog (`list_verticals`, `list_services_by_vertical`, `list_products_by_vertical`, `register_lead_note`, `set_lead_status`, `resolve_or_create_contact`); las de scheduling (`book_appointment`/`check_availability`) NO se seedean (se cablean cuando #7 ship). La UI no debe sugerir que una tool no registrada "funciona".

#### Estados (Pantalla 2)

- **Empty (sin herramientas)**:
```
┌────────────────────────────────────────────────────────────────────┐
│                       🔧  (WrenchRegular)                            │
│                  Aún no hay herramientas                             │
│      Crea herramientas (acciones de crm/catálogo) para que tus      │
│      bots puedan ejecutarlas durante una conversación.              │
│                    [ + Nueva herramienta ]                          │
└────────────────────────────────────────────────────────────────────┘
```
> (Improbable en prod: el seed de F2 carga las 5–6 tools de crm/catalog.)
- **Loading (primera carga)**: DataTable con 5 skeleton rows.
- **No-results (filtro sin matches)**: "No hay herramientas con los filtros actuales."
- **Refetching (background)**: tabla `opacity: 0.55` + spinner top-right.
- **Guardando (drawer)**: footer disabled; fields disabled.
- **Error 409 (`BOT_TOOL_CODE_TAKEN`)**: `<MessageBar intent="error">` + error inline en `code`.
- **Error JSON Schema inválido**: bloqueo client-side antes de enviar (no llega al backend); error inline en `parameters_schema`.
- **Error de red**: `<MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.
- **Eliminar herramienta**: `<ConfirmDialog destructive>` — "¿Eliminar la herramienta '{nombre}'? Los bots que la tengan asignada dejarán de poder invocarla. Las llamadas registradas se conservan." (soft-delete; los `BotToolCall` quedan como audit). Si la tool está asignada a algún bot, el backend puede responder un guard (si se implementa `BOT_TOOL_IN_USE`); el MVP usa soft-delete + el M:N se limpia al re-guardar el bot. Preferir el toggle **Activa** para "deshabilitar sin borrar".

#### Componentes Fluent UI (Tools)

| Concepto UI | Componente |
|---|---|
| Lista | `<DataTable<BotToolItem>>` + `useTableQuery({ queryKey: "bots:tools" })` |
| Badge confirmación | `<Badge color="warning">` "⚠ Sí" / "—" |
| Badge no registrada | `<Badge color="warning">` "No registrada" (si `is_registered=false`) + `<Tooltip>` |
| Badge estado | `<StatusBadge>` "Activo"/"Inactivo" (**reuse** crm) |
| Drawer | `<Drawer size="medium">` (del template) |
| Campos | `<FormField>` + `<Input>` / `<Textarea>` / `<Switch>` vía `Controller` |
| Editor JSON Schema | `<Textarea>` mono autosize + validación parse client-side (sin librería de editor compleja; si se desea resaltado, evaluar un editor liviano sin romper Fluent) |
| Servicio destino | `<Input>` mono + `<Tooltip>` (truncado en la tabla) |
| Row menu | `<RowActions item={t} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive />` |
| Empty / error | `<EmptyState>` + `<MessageBar intent="error">` |

---

### Pantalla 3 — `/bots/depuracion` (panel de observabilidad read-only por conversación)

> **HONESTIDAD (binding por la spec §9)**: este es el **componente más pesado de `bots`** (análogo en peso, no en forma, al Timeline de `crm` y al inbox de `conversations`). Es **100 % read-only** (la traza es audit inmutable, sin SoftDelete) salvo dos acciones server-side de admin: **"Reiniciar estado"** (`BOT_STATE_WRITE`) y **"Disparar turno (debug)"** (`BOT_ENGINE_INVOKE`). NO hay UI de chat ni el browser invoca el LLM. Se construye con primitivos Fluent (`Card`, `Badge`, `Spinner`, `Skeleton`, `MessageBar`, `Tooltip`, `Accordion`, `Divider`, `DataGrid`/lista) + tokens del design system. **NO se usa librería externa de trace/LLM-ops.** El lenguaje visual se inspira en LangSmith/Langfuse/OpenAI Playground (turnos cronológicos con métricas + spans de tool calls anidados) pero **enteramente dentro de Fluent**.

#### Entrada a la pantalla

- **Con `?conv=<id>`** (deep-link, t.ej. desde el botón "Ver depuración del bot" del hilo en conversations): carga directa de la traza de esa conversación.
- **Sin `?conv=`** (item de nav): muestra un **selector de conversación** — un `<Input>`/buscador que acepta pegar/seleccionar un `conversation_id` (o, opcionalmente, una lista corta de "conversaciones atendidas por bot recientemente" si el backend la expone; MVP: input + deep-link). Empty: "Selecciona una conversación para depurar su bot."

#### Anatomía — mockup del panel (estado normal, una conversación con bot)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  Depuración del bot                                                                         │
│  Conversación atendida por: Bot de Preventa · v3 · OpenAI (gpt-4.1-mini)                   │
│  Contacto: Ana Torres · 📱 WhatsApp · +51 999 111 222     [ Ver conversación ↗ ]           │
│ ┌────────────────────────────────────┬─────────────────────────────────────────────────┐ │
│ │  ESTADO DEL BOT (panel izq ~340px) │  TIMELINE DE TURNOS (panel der, resto)          │ │
│ │ ┌────────────────────────────────┐ │ ┌─────────────────────────────────────────────┐ │ │
│ │ │ Intención: consultar_precio    │ │ │ ── Hoy ────────────────────────────────────  │ │ │
│ │ │ Turnos: 3                      │ │ │ ┌─────────────────────────────────────────┐ │ │ │
│ │ │ Versión: v3 · OpenAI           │ │ │ │ ● Turno 3 · completado    2:16 p. m.    │ │ │ │
│ │ │ Último turno: hace 2 min       │ │ │ │   tokens ↑820 ↓210 · 1.4s · $0.0008     │ │ │ │
│ │ │ Último nodo: cierre_lead       │ │ │ │   in:  "¿cuánto cuesta la limpieza?"    │ │ │ │
│ │ │ ──────────────────────────────  │ │ │ │   out: "La limpieza cuesta S/120…"      │ │ │ │
│ │ │ Datos capturados (slots)       │ │ │ │   ┌─ Llamada a herramienta ───────────┐ │ │ │ │
│ │ │ ┌────────────────────────────┐ │ │ │ │   │ list_services_by_vertical  ✓ Éxito│ │ │ │ │
│ │ │ │ servicio: "limpieza dental"│ │ │ │ │   │ args {vertical_id:"dental"} · 240ms│ │ │ │ │
│ │ │ │ interes:  "alto"           │ │ │ │ │   │ result [3 servicios] ▸ ver        │ │ │ │ │
│ │ │ └────────────────────────────┘ │ │ │ │   └────────────────────────────────────┘ │ │ │ │
│ │ │ ──────────────────────────────  │ │ │ └─────────────────────────────────────────┘ │ │ │
│ │ │ [ Reiniciar estado ]           │ │ │ ┌─────────────────────────────────────────┐ │ │ │
│ │ │ [ Disparar turno (debug) ]     │ │ │ │ ⚠ Turno 2 · fallido       2:15 p. m.    │ │ │ │
│ │ └────────────────────────────────┘ │ │ │   error: PROVIDER_ERROR (timeout)       │ │ │ │
│ │                                    │ │ │ └─────────────────────────────────────────┘ │ │ │
│ │                                    │ │ │ ┌─────────────────────────────────────────┐ │ │ │
│ │                                    │ │ │ │ ● Turno 1 · completado    2:14 p. m.    │ │ │ │
│ │                                    │ │ │ │   tokens ↑420 ↓130 · 0.9s · $0.0005     │ │ │ │
│ │                                    │ │ │ └─────────────────────────────────────────┘ │ │ │
│ │                                    │ │ │           (scroll, descendente)             │ │ │
│ └────────────────────────────────────┴─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

> Leyenda: `●` (verde, `colorPaletteGreenForeground1`) = turno completado; `⚠` (rojo, `colorPaletteRedForeground1`) = turno fallido; `↑` tokens de entrada (`tokens_in`), `↓` tokens de salida (`tokens_out`); el separador "Hoy" es **client-only** (TZ). Las llamadas a herramienta (`BotToolCall`) van **anidadas** bajo su turno/evento.

#### Panel izquierdo — Estado del bot (`ConversationBotState`)

Tarjeta read-only que mapea `GET /conversations/{cid}/state` → `ConversationBotStateDetail`:
- **Intención** (`current_intent`) — texto libre o "—" si NULL.
- **Turnos** (`turn_count`).
- **Versión** (`bot_configuration_version_id` → "v{n} · {Proveedor}", la versión con la que arrancó — **no necesariamente la vigente**; tooltip "Versión con la que arrancó esta conversación; activar otra versión no migra las conversaciones en curso").
- **Último turno** (`last_bot_turn_at` → `formatRelative`, client-only) — "—" si nunca.
- **Último nodo** (`last_node`) — "—" si NULL.
- **Datos capturados (slots)** (`collected_slots`, JSON) — render como lista clave→valor (no JSON crudo si es plano; `<pre>` colapsable si es anidado/grande). Empty: "Sin datos capturados todavía."
- **Acciones (gated)**:
  - **"Reiniciar estado"** (`<Button appearance="subtle">`, gated `BOT_STATE_WRITE`) → `POST /conversations/{cid}/state/reset`. `<ConfirmDialog>`: "¿Reiniciar el estado del bot para esta conversación? Se borrarán la intención, los datos capturados y el contador de turnos. La traza de eventos se conserva." (no destruye `BotEvent`/`BotToolCall` — solo el `ConversationBotState`). Tras reiniciar: refetch del panel.
  - **"Disparar turno (debug)"** (`<Button appearance="subtle">`, gated `BOT_ENGINE_INVOKE`) → `POST /engine/dispatch-manual { conversation_id, input_message_id? }`. `<ConfirmDialog>`: "¿Disparar un turno del bot manualmente? El bot procesará el último mensaje del hilo y podría responder al contacto." (⚠ puede enviar un mensaje real al contacto — copy honesto). Tras disparar: indicador "Procesando turno…" (el dispatch es async vía Cloud Tasks; el resultado aparece en el timeline cuando el motor termina — refetch/poll suave del timeline por unos segundos, o un toast "Turno encolado; refresca para ver el resultado"). Pensado para QA/debug, no operación normal.

> **HONESTIDAD (binding spec §0.1)**: el turno corre **async** (Cloud Tasks → `/engine/dispatch` OIDC; ADR-012), **no** síncrono en la request del browser. "Disparar turno (debug)" **encola** (o dispara) el turno; el panel NO bloquea esperando el LLM. El resultado se ve en el timeline tras la conclusión (refetch suave). No prometer respuesta inmediata.

#### Panel derecho — Timeline de turnos (`BotEvent`) + llamadas a herramienta (`BotToolCall`)

Feed cronológico **descendente** (lo más nuevo arriba — molde Timeline de crm, contrario al hilo de chat de conversations que va ascendente), agrupado por día (encabezados "Hoy"/"Ayer"/"{DD mmm}" **client-only**). Mapea `GET /conversations/{cid}/events` → `BotEventItem[]` + `GET /conversations/{cid}/tool-calls` → `BotToolCallItem[]` (anidadas por `bot_event_id`/`turn_number`).

**Tarjeta de evento (`BotEventCard`, memoizada)** — una por `BotEvent` (típicamente uno `turn_started` + uno `turn_completed`/`turn_failed` por turno; el front puede **colapsar** el par en una "tarjeta de turno" que muestra el `event_type` final + métricas, con `tool_dispatched` como spans internos):
- **Encabezado**: glifo de estado (`●` verde completado / `⚠` rojo fallido / `◔` neutral iniciado-en-curso / `🔧` invocó herramienta) + "Turno {turn_number} · {event_type traducido}" + `formatRelative(created_on)` (client-only) + hora absoluta en tooltip.
- **Métricas** (cuando aplica, `turn_completed`): "tokens ↑{tokens_in} ↓{tokens_out} · {latency_ms→s} · ${cost_estimated_usd}" — `cost_estimated_usd` con `numeric(10,6)`, formatear a 4 decimales; "—" si NULL.
- **Mensajes del turno**: `input_message_id`/`output_message_id` son **mids de Firestore (varchar, NO FK; ADR-011)**. El panel muestra un **preview del contenido** del inbound/outbound si lo resuelve (lectura del doc Firestore `conversations/{cid}/messages/{mid}` server-side, o desde el hilo ya cargado en conversations); si no puede resolverlo, muestra el `mid` (mono, truncado) con tooltip "Identificador del mensaje en el hilo". (MVP mínimo: mostrar los mids; el preview es un nice-to-have si el backend los hidrata en el item.)
- **Error** (`turn_failed`): `<MessageBar intent="error">` con el `error` (texto) + el `event_type`. Color rojo (`colorPaletteRedForeground1`).
- **`metadata`** (raw provider response/fingerprint): bajo un `<Accordion>`/"Ver detalle" colapsado → `<pre>` con el JSON (read-only). No expandido por default (ruido).

**Span de llamada a herramienta (`BotToolCallCard`, memoizada)** — anidada bajo su turno/evento:
- **Encabezado**: ícono 🔧 + `bot_tool` (code/name) + badge de **status** (Pendiente/Éxito/Error/Tiempo agotado, color por estado) + latencia (`latency_ms`).
- **Argumentos** (`arguments`, JSON): preview de 1 línea (truncado) + "▸ ver" → `<Accordion>` con el JSON completo.
- **Resultado** (`result`, JSON, nullable): "▸ ver" → `<Accordion>` con el JSON; o un resumen ("[3 servicios]") si el front lo deriva.
- **Error** (`error_message`, si `status in {error,timeout}`): `<MessageBar intent="error">` con el mensaje. El caso `TOOL_NOT_REGISTERED` (tool diseñada pero no seedeada) se ve aquí como un tool call en error con "El servicio destino no está registrado."
- `tool_use_id` (mono, en tooltip) para matching multi-tool — útil al depurar turnos con varias herramientas.

**Estados de `BotToolCall`** — badge + glifo + color (token):

| `status` | Glifo | Copy | Color (token) |
|---|---|---|---|
| `pending` | `🕓` | "Pendiente" | `tokens.colorNeutralForeground3` |
| `success` | `✓` | "Éxito" | `tokens.colorPaletteGreenForeground1` |
| `error` | `✕` | "Error" | `tokens.colorPaletteRedForeground1` |
| `timeout` | `⏱` | "Tiempo agotado" | `tokens.colorPaletteRedForeground1` |

**Estados de `BotEvent` (event_type)** — badge + glifo + color:

| `event_type` | Glifo | Copy | Color (token) |
|---|---|---|---|
| `turn_started` | `◔` | "Turno iniciado" | `tokens.colorNeutralForeground3` |
| `turn_completed` | `●` | "Turno completado" | `tokens.colorPaletteGreenForeground1` |
| `turn_failed` | `⚠` | "Turno fallido" | `tokens.colorPaletteRedForeground1` |
| `tool_dispatched` | `🔧` | "Herramienta invocada" | `tokens.colorPaletteBlueForeground2` |
| `handoff_triggered` | `→` | "Handoff disparado" | `tokens.colorPaletteYellowForeground1` (futuro — no ocurre en MVP) |

**Day-groups + "Hoy/Ayer" (client-only — lección TZ)**: igual que el Timeline de crm — el cálculo de "hoy"/"ayer" se hace **client-only** (`"use client"` + `useMemo`/`useEffect` montado en cliente). Dentro de cada grupo, los turnos van **descendentes por `created_on`** (lo más nuevo arriba — molde crm).

#### Estados (Pantalla 3)

- **Loading (estado + timeline)**: panel izq con tarjeta skeleton (4 líneas + bloque slots); panel der con 4–5 `BotEventCard` skeleton.
- **Empty — sin `?conv=`**: "Selecciona una conversación para depurar su bot." + el selector/input de `conversation_id`.
- **Empty — conversación sin estado de bot** (`BOT_STATE_NOT_FOUND` 404): la conversación existe pero nunca la atendió un bot (`assignee_type != 'bot'` o aún sin turnos). Panel izq: "Esta conversación no tiene estado de bot. No ha sido atendida por un bot todavía." Panel der: "Sin eventos del bot." (No es un error — es un empty legítimo; el backend devuelve 404 `BOT_STATE_NOT_FOUND` y el front lo trata como empty, no como error.)
- **Empty — sin eventos** (estado existe pero `BotEvent` vacío): timeline "Sin turnos registrados todavía."
- **Error (5xx)**: `<MessageBar intent="error">"No se pudo cargar la depuración."` + botón "Reintentar".
- **Refetching (tras Reiniciar/Disparar)**: refetch silencioso del panel afectado (no spinner global); indicador sutil "Actualizando…".
- **Disparar turno encolado**: toast/`MessageBar intent="info"` "Turno encolado. El resultado aparecerá en el timeline en unos segundos." + refetch suave del timeline (~3–5 s, unas pocas veces; NO polling permanente — esta pantalla no es real-time como el inbox; el debug es puntual).
- **Sin permiso de escritura (ASESOR / sin `BOT_STATE_WRITE`/`BOT_ENGINE_INVOKE`)**: el panel se ve completo en **read** (estado + timeline), pero los botones "Reiniciar estado" y "Disparar turno (debug)" **no se renderizan** (gated). El ASESOR con `BOT_EVENTS_READ`/`BOT_STATE_READ`/`BOT_TOOL_CALLS_READ` ve toda la traza, sin acciones.
- **Sin permiso de lectura**: `requirePermission("BOT_EVENTS_READ")` en `page.tsx` → redirect (no llega a renderizar).

#### Performance (reglas vercel-react — binding)

> Una conversación de bot puede acumular decenas de turnos y cientos de tool calls. Reglas (skill vercel-react-best-practices):
- **`BotEventCard` y `BotToolCallCard` memoizadas** (`React.memo`) — el refetch tras un debug no debe re-renderizar todo el timeline. Reconciliar por `id`; props estables; handlers (expandir args/result) vía `useCallback`.
- **`content-visibility: auto`** + `contain-intrinsic-size` en cada tarjeta de turno (CSS via `makeStyles`) → el navegador no paga layout/paint de lo que está fuera del viewport (igual que el Timeline de crm).
- **`useMemo` para la agrupación por día** y para el merge de `BotEvent` + `BotToolCall` (anidar las tool calls bajo su `bot_event_id`/`turn_number` una sola vez, no en cada render).
- **JSON colapsado por default** (args/result/metadata bajo `<Accordion>`) — no renderizar `<pre>` grandes hasta que el usuario los abre.
- **Sin polling permanente** — a diferencia del inbox, Depuración NO es real-time; el único refetch automático es la ventana corta tras "Disparar turno". El `page.tsx` (RSC) prefetcha el estado + la primera página de eventos cuando hay `?conv=`.

#### Componentes Fluent UI (Depuración)

| Concepto UI | Componente |
|---|---|
| Layout 2 paneles | `BotDebugShell` (custom) — grid `340px 1fr` (`makeStyles`), responsive (colapsa a una vista en mobile) |
| Header (bot + contacto) | `<div>` + `BotProviderBadge` + `ChannelIcon` (**reuse** crm) + link "Ver conversación ↗" (a `/conversaciones/bandeja?conv=<id>`, gated `CONVERSATIONS_READ`) |
| Selector de conversación | `<Input>` (`conversation_id`) + `nuqs useQueryState("conv")` |
| Tarjeta de estado | `<Card>` read-only — intención/turnos/versión/último turno/nodo + slots |
| Slots (clave→valor) | lista `<div>` clave→valor; `<pre>`/`<Accordion>` si anidado |
| Acción reiniciar | `<Button appearance="subtle">` "Reiniciar estado" + `<ConfirmDialog>` (gated `BOT_STATE_WRITE`) |
| Acción disparar | `<Button appearance="subtle">` "Disparar turno (debug)" + `<ConfirmDialog>` (gated `BOT_ENGINE_INVOKE`) |
| Timeline | feed `<div>` por día (molde Timeline de crm) |
| Encabezado de día | `DayGroup` (custom, "use client", cálculo hoy/ayer **client-only**) — **reuse** del de conversations/crm si está extraído |
| Tarjeta de turno/evento | `BotEventCard` (custom, memoizada) — glifo + métricas + mensajes + error + metadata colapsable |
| Badge event_type | `<Badge>` por `event_type` (color/glifo de la tabla) |
| Métricas | texto + `<Tooltip>` (tokens/latencia/costo) |
| Span tool call | `BotToolCallCard` (custom, memoizada, anidada) |
| Badge tool status | `<Badge>` por `status` (color/glifo de la tabla) |
| Args / result / metadata | `<Accordion>` + `<pre>` (JSON colapsado) |
| Error | `<MessageBar intent="error">` (turno fallido / tool error / TOOL_NOT_REGISTERED) |
| Timestamp relativo | `formatRelative(iso)` (**reuse**, client-only) + `<Tooltip>` con hora absoluta |
| Skeletons | `<Skeleton>` + `<SkeletonItem>` |
| Empty / error | `<EmptyState>` + `<MessageBar>` |
| Perf | `React.memo` + `useCallback` + CSS `contentVisibility:"auto"` + `containIntrinsicSize` |

---

## Decisiones de UI (cierres)

### Configuraciones = drawer con tabs (Datos · Versiones · Herramientas), no página-detalle
Regla-precedente de clinic/staff/crm/conversations: entidad con **un** sub-recurso de interacción propia (versiones del prompt) + uno liviano (tools M:N) → drawer ancho con tabs, no página-detalle completa (eso se reserva a `Person`, que tiene varias superficies densas). El tab Versiones es la pieza bespoke (editor de prompt grande + provider/model/params + "Activar"). El prompt **nunca se edita in-place** — cada cambio es una versión nueva (historial inmutable + promoción explícita por "Activar"). Misma filosofía que los catálogos configurables de crm.

### La traza del bot es observabilidad read-only (audit inmutable), no edición
`BotEvent`/`BotToolCall` no llevan SoftDelete (spec §2) — son audit. La pantalla de Depuración los **muestra**, no los edita. Las únicas mutaciones son **server-side**: "Reiniciar estado" (`BOT_STATE_WRITE`) borra el `ConversationBotState` (no la traza) y "Disparar turno (debug)" (`BOT_ENGINE_INVOKE`) **encola** un turno (async, Cloud Tasks; no bloquea ni promete respuesta inmediata). El browser **nunca** habla con el LLM ni dispara cómputo directo. El espíritu del feed (por día, client-only, tarjetas tipadas, `React.memo`+`content-visibility`) se **reusa** del Timeline de crm; no se introduce librería de trace.

### El secreto del proveedor nunca llega al front (binding spec §0.7)
Las API keys (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) son **globales por entorno** (Settings, vía `--set-secrets` de Cloud Run) — **no** hay campo de API key por bot/versión en la UI. La versión solo configura `provider` + `model_name` + `parameters`; las credenciales las resuelve el backend. Misma disciplina que `conversations` con el secreto del canal (que tampoco llega al front). El `external_webhook_secret_name` existe en el modelo pero su provider está **diferido** (F4) → sus campos no se renderizan en el MVP.

### Provider/model como datos, no como secreto; default OpenAI `gpt-4.1-mini` (binding spec §0.2)
El dropdown de proveedor habilita **OpenAI (default) y Claude** en el MVP; el resto (`vertex_ai`/`azure_openai`/`external_webhook`) se listan **deshabilitados** con "(próximamente)" para dejar el roadmap visible (un provider sin adaptador da `PROVIDER_NOT_SUPPORTED` 400 en runtime). El `model_name` es texto libre con default sugerido por provider. Mismo patrón que conversations con los `ChannelType` no-WhatsApp deshabilitados.

### Las tools diseñadas-pero-no-registradas se listan, no se ocultan (binding spec §0.4)
El catálogo de Tools permite `target_service` apuntando a módulos inexistentes (ej. `scheduling.*`) — deliberado, deja el roadmap visible — pero esas tools dan `TOOL_NOT_REGISTERED` (404 runtime) si un bot las invoca. La UI lo hace honesto con un badge "No registrada" (si el item trae `is_registered`) y un copy claro; **no** sugiere que "funcionan". El MVP seedéa solo las de crm/catalog.

### `router.refresh()` + refetch en toda mutación de denormalizados (lección crm F3)
Activar una versión cambia "Versión vigente" en la fila de la lista **y** en el tab Datos del drawer; editar el M:N de tools no afecta la lista pero sí el tab; reiniciar estado / disparar turno afectan el panel de Depuración. Tras cada mutación: refetch del recurso afectado + `router.refresh()` cuando toca datos que otra superficie muestra (la columna "Versión vigente" de la lista) — sin esto el badge queda **stale** (bug MAJOR cazado en crm F3).

### Disparar turno NO bloquea (async Cloud Tasks, binding spec §0.1 + ADR-012)
"Disparar turno (debug)" **encola** vía Cloud Tasks (o dispara el endpoint interno); la UI muestra "Turno encolado; el resultado aparecerá en el timeline en unos segundos" + refetch suave acotado (no polling permanente — Depuración no es real-time). Copy honesto: el dispatch puede **enviar un mensaje real al contacto** (confirm explícito). No prometer respuesta inmediata ni simular un chat en vivo.

### "Hoy"/fechas relativas siempre client-only (TZ)
Toda fecha que afecte el render (agrupación del timeline por día, "hace 2 min", "Hoy"/"Ayer", "último turno") se computa **client-only** (`useEffect`/`useMemo` montados en cliente, no en SSR). Se **reusa** `formatRelative(iso)` de `lib/utils/date.ts` (creado en crm). El servidor en UTC desfasaría el día en Lima (UTC-5) — bug recurrente de staff/crm/conversations.

### Editor JSON Schema / parámetros = `<Textarea>` mono + validación, sin librería pesada
`parameters_schema` (BotTool) y `parameters` (versión) se editan como JSON en un `<Textarea>` mono con validación parse client-side (debe parsear a objeto; error inline si no). Sin introducir un editor de código pesado (Monaco/CodeMirror) en el MVP — mantenerse dentro de Fluent. Si negocio lo pide, evaluar un editor liviano después sin romper el design system.

### Sin i18n framework por ahora
Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm/conversations). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive
Mismo criterio que clinic/staff/crm/conversations (template optimizado para desktop interno): sidebar colapsado por default. Las DataTables (Configuraciones, Tools) scrollean horizontal; los drawers van a 100 % del width en mobile. El **panel de Depuración de 2 paneles** colapsa a una vista en pantallas angostas: primero el Estado del bot, luego el Timeline (tab o stack vertical) — no ambos lado a lado. El editor de prompt usa textarea a ancho completo.

### Accesibilidad básica
- La lista de versiones y el timeline de eventos son navegables por teclado; las tarjetas de turno exponen su `event_type`/estado a lectores de pantalla (`aria-label` "Turno 3, completado, hace 2 minutos").
- El estado de evento/tool (`●`/`⚠`/`✓`/`✕`) no se comunica **solo** por color/glifo: cada uno tiene `aria-label`/`<Tooltip>` con el texto ("Turno completado", "Error").
- Los `<Accordion>` de args/result/metadata son operables por teclado y anuncian expandido/colapsado.
- El editor de prompt (`<Textarea>`) tiene `aria-label`; el editor JSON anuncia el error de parseo (`aria-describedby`).
- Contraste de los badges de provider/estado verificado con tokens semánticos (no colores hardcodeados).

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, claves de JSON/parameters, CSS classes) en inglés — solo los textos visibles van traducidos. Glosario y género en la tabla del inicio: **Configuración / Versión / Herramienta / Intención / Llamada / Latencia** femeninos; **Bot / Proveedor / Modelo / Prompt / Parámetro / Servicio / Turno / Evento / Esquema / Estado / Costo / Slot** masculinos.

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Nav — | |
| Grupo | "Bots" |
| Item configuraciones | "Configuraciones" |
| Item herramientas | "Herramientas" |
| Item depuración | "Depuración" |
| — Configuraciones (Pantalla 1) — | |
| Page title | "Configuraciones de bot" |
| Page subtitle | "Define los bots que atienden automáticamente tus conversaciones." |
| Botón crear | "+ Nuevo bot" |
| Columnas | "Código" / "Nombre" / "Tipo" / "Versión vigente" / "Estado" |
| Badge tipo | "Preventa" / "Postventa" / "General" / "Personalizado" |
| Versión vigente (sin) | "— sin versión" |
| Bot sin versión (hint) | "Crea y activa una versión para que el bot pueda responder." |
| Drawer tabs | "Datos" / "Versiones" / "Herramientas" |
| Drawer title | "{nombre del bot}" / "Nuevo bot" |
| Label código | "Código" |
| Label nombre | "Nombre" |
| Label tipo | "Tipo de bot" |
| Label descripción | "Descripción" |
| Label máx. turnos | "Máx. turnos por conversación" |
| Hint máx. turnos | "Vacío = sin límite. Guard opcional para evitar bucles largos." |
| Versión vigente (read en Datos) | "Versión vigente: v{n} · {Proveedor} ({modelo})" |
| Aviso editar prompt | "El prompt y los parámetros se editan creando una nueva versión (pestaña Versiones)." |
| Toggle activo | "Activo" |
| Error 409 (código) | "Ya existe un bot con este código." |
| Confirm delete title | "¿Eliminar bot?" |
| Confirm delete body | "¿Eliminar el bot '{nombre}'? Las conversaciones que esté atendiendo dejarán de recibir respuestas automáticas. La traza de eventos se conserva." |
| Empty (sin bots) | "Aún no hay bots. Crea un bot para que atienda automáticamente las conversaciones entrantes de tus canales." |
| — Versiones (tab) — | |
| Título | "Versiones" |
| Botón nueva | "+ Nueva versión" |
| Badge vigente | "Vigente" |
| Badge activa/inactiva | "Activa" / "Inactiva" |
| Acción ver | "Ver versión" |
| Acción activar | "Activar" |
| Confirm activar | "¿Activar la versión v{n}? Las conversaciones nuevas usarán este prompt; las conversaciones en curso mantienen su versión." |
| Empty versiones | "Este bot no tiene versiones todavía. Crea la primera versión con su prompt para poder activarla." |
| — Nueva versión (sub-dialog) — | |
| Title | "Nueva versión — {nombre del bot}" / "Versión v{n}" (read) |
| Label proveedor | "Proveedor" |
| Opción proveedor deshabilitada | "{proveedor} (próximamente)" |
| Label modelo | "Modelo" |
| Hint modelo | "Depende del proveedor. Ej.: gpt-4.1-mini, claude-3-5-sonnet-latest." |
| Label prompt | "Prompt de sistema" |
| Label parámetros | "Parámetros (JSON)" |
| Hint parámetros | "Esquema libre por proveedor (temperature, max_tokens, top_p…). Vacío = {}." |
| Error parámetros inválidos | "Parámetros: JSON inválido." |
| Label notas | "Notas (changelog, opcional)" |
| Checkbox activar al crear | "Activar esta versión al crearla" |
| Botón crear versión | "Crear versión" / "Creando…" |
| Botón crear a partir de | "Crear nueva a partir de esta" |
| — Herramientas del bot (tab) — | |
| Título | "Herramientas que este bot puede usar" |
| Search placeholder | "Buscar herramientas…" |
| Marca confirmación | "⚠ = requiere confirmación." |
| Ayuda | "El bot solo podrá invocar las herramientas marcadas." |
| Empty catálogo | "Aún no hay herramientas. Crea herramientas en la sección Herramientas para asignarlas a este bot." |
| Toast guardado | "Herramientas actualizadas." |
| — Herramientas (Pantalla 2) — | |
| Page title | "Herramientas" |
| Page subtitle | "Acciones que un bot puede invocar durante una conversación." |
| Botón crear | "+ Nueva herramienta" |
| Columnas | "Código" / "Nombre" / "Servicio destino" / "Confirmación" / "Estado" |
| Badge confirmación | "⚠ Sí" / "—" |
| Badge no registrada | "No registrada" |
| Tooltip no registrada | "El servicio destino no está disponible en este entorno; invocarla dará error." |
| Drawer title | "Nueva herramienta" / "Editar herramienta" / "Herramienta" |
| Label código | "Código" |
| Label nombre | "Nombre" |
| Label descripción | "Descripción" |
| Hint descripción | "La lee el modelo para decidir cuándo invocar esta herramienta. Sé claro y específico." |
| Label esquema | "Esquema de parámetros (JSON Schema)" |
| Hint esquema | "Subset común OpenAI/Anthropic (JSON Schema). Define los argumentos que el bot debe pasar." |
| Error esquema inválido | "Esquema de parámetros: JSON inválido." |
| Label servicio destino | "Servicio destino" |
| Hint servicio destino | "Identifica la función del backend que ejecuta la herramienta. Ej.: crm.person_lead_status.transition." |
| Toggle confirmación | "Requiere confirmación" |
| Hint confirmación | "Si está activo, las acciones de esta herramienta requerirán confirmación antes de ejecutarse." |
| Toggle activa | "Activa" |
| Error 409 (código) | "Ya existe una herramienta con este código." |
| Confirm delete title | "¿Eliminar herramienta?" |
| Confirm delete body | "¿Eliminar la herramienta '{nombre}'? Los bots que la tengan asignada dejarán de poder invocarla. Las llamadas registradas se conservan." |
| Empty (sin herramientas) | "Aún no hay herramientas. Crea herramientas (acciones de crm/catálogo) para que tus bots puedan ejecutarlas durante una conversación." |
| — Depuración (Pantalla 3) — | |
| Page title | "Depuración del bot" |
| Header bot | "Conversación atendida por: {nombre del bot} · v{n} · {Proveedor} ({modelo})" |
| Header contacto | "Contacto: {nombre} · {canal} · {identificador}" |
| Link a conversación | "Ver conversación ↗" |
| Selector (empty) | "Selecciona una conversación para depurar su bot." |
| Panel estado: intención | "Intención" |
| Panel estado: turnos | "Turnos" |
| Panel estado: versión | "Versión" |
| Tooltip versión | "Versión con la que arrancó esta conversación; activar otra versión no migra las conversaciones en curso." |
| Panel estado: último turno | "Último turno" |
| Panel estado: último nodo | "Último nodo" |
| Panel estado: slots | "Datos capturados (slots)" |
| Slots empty | "Sin datos capturados todavía." |
| Botón reiniciar | "Reiniciar estado" |
| Confirm reiniciar | "¿Reiniciar el estado del bot para esta conversación? Se borrarán la intención, los datos capturados y el contador de turnos. La traza de eventos se conserva." |
| Botón disparar | "Disparar turno (debug)" |
| Confirm disparar | "¿Disparar un turno del bot manualmente? El bot procesará el último mensaje del hilo y podría responder al contacto." |
| Turno encolado | "Turno encolado. El resultado aparecerá en el timeline en unos segundos." |
| Timeline título | "Timeline de turnos" |
| Turno (encabezado) | "Turno {n} · {estado}" |
| Métricas | "tokens ↑{in} ↓{out} · {latencia} · ${costo}" |
| Mensaje entrada | "Entrada" / "in" |
| Mensaje salida | "Salida" / "out" |
| Ver detalle (metadata) | "Ver detalle" |
| Llamada a herramienta (encabezado) | "Llamada a herramienta" |
| Ver args/result | "Ver argumentos" / "Ver resultado" |
| Event: turno iniciado | "Turno iniciado" |
| Event: turno completado | "Turno completado" |
| Event: turno fallido | "Turno fallido" |
| Event: herramienta invocada | "Herramienta invocada" |
| Event: handoff disparado | "Handoff disparado" |
| Tool status pendiente | "Pendiente" |
| Tool status éxito | "Éxito" |
| Tool status error | "Error" |
| Tool status timeout | "Tiempo agotado" |
| Empty sin estado | "Esta conversación no tiene estado de bot. No ha sido atendida por un bot todavía." |
| Empty sin eventos | "Sin turnos registrados todavía." |
| Error carga | "No se pudo cargar la depuración." |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Status badge | "Activo" / "Inactivo" |
| Loading placeholder | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |
| Encabezados de día (timeline) | "Hoy" / "Ayer" / "{DD mmm YYYY}" |
| Botón cancelar / cerrar | "Cancelar" / "Cerrar" |
| Botón guardar / guardando | "Crear" / "Creando…" · "Guardar" / "Guardando…" |

### Concordancia de género

- **Configuración / Versión / Herramienta / Intención / Llamada / Latencia** son **femeninos**: "la configuración", "esta versión está activa", "la herramienta", "la intención", "la llamada falló", "la latencia".
- **Bot** es **masculino** la entidad operativa ("el bot", "este bot", "el bot de preventa"); el ítem de nav y los títulos usan "Configuraciones de bot".
- **Proveedor / Modelo / Prompt / Parámetro / Servicio / Turno / Evento / Esquema / Estado / Costo / Slot** son **masculinos**: "el proveedor", "el modelo", "el prompt de sistema", "los parámetros", "el servicio destino", "el turno", "el evento", "el esquema de parámetros", "el estado del bot", "el costo estimado".

### Etiquetas de proveedor (`BotProvider`) — `BotProviderBadge`

`key` (slug) en inglés, etiqueta visible en español/marca. Color por provider (token o hex curado; **no** `accent`). MVP habilita OpenAI + Claude; el resto se lista deshabilitado:

| `provider` | Etiqueta | Color (sugerido) | MVP |
|---|---|---|---|
| `openai` | "OpenAI" | `colorPaletteGreenForeground1` / neutro | ✅ habilitado (default) |
| `claude` | "Claude" | `colorPaletteBrownForeground2` / `tokens.colorPalettePeachForeground2` | ✅ habilitado |
| `vertex_ai` | "Vertex AI" | `colorPaletteBlueForeground2` | (próximamente) |
| `azure_openai` | "Azure OpenAI" | `colorPaletteBlueForeground2` | (próximamente) |
| `external_webhook` | "Webhook externo" | `colorNeutralForeground3` | (próximamente — F4) |

### Etiquetas de tipo de bot (`BotType`)

| `bot_type` | Etiqueta | Color (sugerido) |
|---|---|---|
| `preventa` | "Preventa" | `colorPaletteBlueForeground2` |
| `postventa` | "Postventa" | `colorPaletteGreenForeground1` |
| `general` | "General" | `colorNeutralForeground2` |
| `custom` | "Personalizado" | `colorPalettePurpleForeground2` |

> No usar logos de marca (OpenAI/Anthropic) — Fluent no los trae y meter SVGs de marca rompe la consistencia del design system. Íconos genéricos + etiqueta de texto bastan (misma decisión que crm/conversations con los canales).

## Mapeo a fases de implementación (checklist de UI F0–F4)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md) y la spec §8 F0–F4). Cada checkbox es una tarea de UI.

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: grupo "Bots" en `NAV_ITEMS` con 3 children (Configuraciones / Herramientas / Depuración), gate `MENU-BOTS` + permiso por child (`BOT_CONFIGURATIONS_READ` / `BOT_TOOLS_READ` / `BOT_EVENTS_READ`); íconos Fluent verificados con fallback (`BotRegular`/`WrenchRegular`/`BugRegular`).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.BOTS` (configurations, configurations/list, configurations/active, configurations/{id}, configurations/{id}/versions, configurations/{id}/versions/{vid}, configurations/{id}/activate-version/{vid}, configurations/{id}/tools, tools, tools/list, tools/{id}, conversations/{cid}/state, conversations/{cid}/state/reset, conversations/{cid}/events, conversations/{cid}/tool-calls, engine/dispatch-manual). El `engine/dispatch` (OIDC, Cloud Tasks) **NO va en el front** — lo invoca Cloud Tasks.
- [ ] `types/bots.types.ts`: todas las interfaces espejo de Pydantic (`BotConfigurationItem`/`Detail`/`Option`/`Create`/`Update`, `BotConfigurationVersionItem`/`Detail`/`Create`, `BotToolItem`/`Detail`/`Create`/`Update`, `ConversationBotStateDetail`, `BotEventItem`, `BotToolCallItem`, `ConfigurationToolsUpdateRequest {tool_ids}`, `DispatchManualRequest`; enums `BotType`/`BotProvider`/`ToolCallStatus`/`BotEventType`).
- [ ] `lib/schemas/bot.schema.ts`: Zod de `botConfigurationSchema` + `botVersionSchema` (incl. validación JSON de `parameters`) + `botToolSchema` (incl. validación JSON Schema de `parameters_schema`).
- [ ] Confirmar **reuse** (no duplicar) de `StatusBadge`, `ChannelIcon` (de crm/conversations), `SearchableOptionList` (de admin/crm), `formatRelative` y `DayGroup` (si extraído). Crear `BotProviderBadge` (nuevo, pequeño).

### F1 — BotConfiguration + Versiones + activate-version (Configuraciones)
- [ ] **Pantalla 1** `/bots/configuraciones`: lista (molde `VerticalsClient`) + `BotConfigurationDrawer` (tabs Datos · Versiones · Herramientas) — tab Datos (CRUD + dedup 409 + máx. turnos) + tab Versiones (lista + `BotVersionDrawer` con editor de prompt/provider/model/params + "Activar versión" + read "Crear nueva a partir de esta") + estados empty/loading/no-results/refetching/error + confirm delete. El tab Herramientas puede quedar inerte/placeholder hasta F2.
- [ ] `BotProviderBadge` (provider → etiqueta + color). `BotType` badges.
- [ ] Migración backend `0017_bots_configuration` (+ forward FK aditivas a channel_account/conversation — no toca UI).

### F2 — BotTool + M:N (Herramientas)
- [ ] **Pantalla 2** `/bots/tools`: lista (molde `VerticalsClient`) + `BotToolDrawer` (create/edit/read) con **editor JSON Schema** de `parameters_schema` + dedup 409 + (opcional) badge "No registrada" + estados empty/loading/no-results/refetching/error + confirm delete.
- [ ] **Tab Herramientas** del drawer del bot (Pantalla 1): `SearchableOptionList` multiselect (**reuse** `StatusMatrixEditor`) → `PUT /configurations/{id}/tools` + empty del catálogo + gating `BOT_CONFIGURATIONS_UPDATE`.
- [ ] Migración backend `0018_bots_tools` (no toca UI).

### F3 — Engine + State + Events + ToolCalls (Depuración)
- [ ] **Pantalla 3** `/bots/depuracion`: `BotDebugShell` de 2 paneles — panel izq (Estado del bot read-only + "Reiniciar estado" gated `BOT_STATE_WRITE` + "Disparar turno (debug)" gated `BOT_ENGINE_INVOKE`) + panel der (Timeline de `BotEvent` por día client-only, `BotEventCard` memoizada con métricas/error/metadata + `BotToolCallCard` anidada con args/result/status) + selector `?conv=` + estados loading/empty (sin `?conv=`, sin estado, sin eventos)/error + "Turno encolado" + refetch suave (no polling permanente).
- [ ] Acceso contextual desde el inbox de `conversations`: botón "Ver depuración del bot" en el header del hilo `assignee_type='bot'` (gated `BOT_EVENTS_READ`) → `/bots/depuracion?conv=<id>`. (Cambio aditivo a la UI de conversations.)
- [ ] Migración backend `0019_bots_engine_state` + enganches conversations (find_or_create_open→bot, send_bot_outbound) + Cloud Tasks (no tocan UI directamente; el "Disparar turno" consume `engine/dispatch-manual`).

### F4 — DIFERIDA (ExternalBotEngine + handoff automático + streaming + cost cap + eval)
- [ ] Provider `external_webhook` habilitado en el dropdown de versión + campos `external_webhook_url`/`external_webhook_secret_name` (hoy ocultos). Handoff automático bot→asesor (`handoff_triggered` deja de ser "futuro"). Streaming del turno (si se construye). Cost cap duro. Framework de evaluación. Fuera del MVP inicial.
