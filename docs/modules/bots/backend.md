# Módulo `bots` — Backend deep-dive

> **Última actualización**: 2026-06-04 (fase de documentación, ANTES de implementar)
> **Audiencia**: developer implementando `backend/app/modules/bots/` (incl. el sub-paquete `services/engine/`) + el cross-cutting nuevo `backend/app/core/cloud_tasks.py` + los **enganches aditivos** a `conversations` (`message.send_bot_outbound`, hook de `find_or_create_open`, enqueue en el webhook processor).
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`../conversations/backend.md`](../conversations/backend.md) (**el molde directo** — CQRS/Firestore, outbox, `send_outbound`, `find_or_create_open`, webhook processor, `secrets.py`/`firestore.py`), [`../crm/backend.md`](../crm/backend.md) (gold-standard: catálogos configurables, matriz, denorm batch sin N+1, `find_by_identifier_or_create`, `lead_activity.log`, ADR-009), [`../../decisions/ADR-005-bot-engine-abstraction.md`](../../decisions/ADR-005-bot-engine-abstraction.md) (**revisado 2026-06-04**: Firestore-no-message-FK, Cloud Tasks dispatch, embedded multi-proveedor OpenAI default, external diferido, enganches conversations), [`../../decisions/ADR-009-forward-fk-deferred-cross-module.md`](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (FKs forward diferidas), [`../../decisions/ADR-010-runtime-secret-resolution.md`](../../decisions/ADR-010-runtime-secret-resolution.md), [`../../decisions/ADR-011-firestore-message-stream-cqrs.md`](../../decisions/ADR-011-firestore-message-stream-cqrs.md) (**el stream de mensajes vive en Firestore — el bot lee el historial del hilo de ahí, NO de Postgres**), y [`../../decisions/ADR-012-cloud-tasks-bot-dispatch.md`](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md) (**NUEVO**: el turno del bot corre async vía Cloud Tasks → endpoint interno OIDC).

> **Contrato autoritativo**: este doc respeta la **spec compartida de `bots`** (`C:/tmp/bots_spec.md` durante la fase de documentación; luego consolidada en [`README.md`](README.md)). Los nombres EXACTOS de entidades/campos/endpoints/permisos/códigos-de-error/enums/fases salen de ahí (en particular las **reconciliaciones §0**, que distinguen el diseño viejo 2026-05-28 del estado real). Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc.

> **Convenciones heredadas de `catalog`/`clinic`/`staff`/`crm`/`conversations` shipped** (repetidas para que este doc se lea solo):
>
> 1. **`PUT` para updates completos** (no `PATCH`). Las versiones de prompt NO se editan in-place: se crea una **nueva versión** y se promueve con `activate-version`.
> 2. **`/active` para dropdowns** → **lista cruda** (`response_model=list[...]`, sin envelope), igual que el resto de módulos.
> 3. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `AlreadyExistsException`, `BadRequestException`, `ForbiddenException`, `ConflictException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; reload-via-`get_by_id`/`get_full` tras create/update; `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` whitelist estricta (campos denormalizados NO server-sortables — lección hotfix `cd10c78` de `staff`).
> 4. **Mensajes `detail` de dominio en español, `code` en inglés**; mensajes de validator Pydantic en inglés (van al 422; el front re-valida con Zod en español). UI 100% español.
> 5. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), lista cruda en `/active`, error `{success:false, detail, code?, errors?}`.
> 6. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `bots` arranca en `0017` (última aplicada = `0016_conv_threads`).
> 7. Patrón **audit users**: `created_by`/`updated_by` explícitos; `*_user: UserAuditInfo | None` hidratado vía `user_repository.get_audit_info_map` batch (sin N+1).
> 8. **Mixins del template** (`app.shared.base_model`): `PrimaryKeyMixin` (`id` varchar(36)), `ActiveMixin` (`active`), `SoftDeleteMixin` (`deleted_at`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **`BotToolCall` y `BotEvent` NO llevan `SoftDeleteMixin`** — son trazas/audit inmutable (no se soft-deletean).
> 9. **JSONB variant**: las columnas `jsonb` usan `JSON().with_variant(JSONB(), "postgresql")` (idéntico a `crm.lead_activity.payload` / `conversations.message_outbox.payload`): JSONB en Postgres (prod), JSON en sqlite (el smoke usa `create_all`, no alembic). La migración escribe `JSONB` (solo corre en Postgres).

`bots` es el **módulo #6** de medisage (catalog→clinic→staff→crm→**conversations COMPLETOS en prod**; sigue bots; luego scheduling #7, marketing #8). Es **el cerebro** que atiende automáticamente una conversación cuando `Conversation.assignee_type='bot'`: arma un prompt con el historial del hilo (leído de **Firestore**, ADR-011), llama a un LLM (OpenAI `gpt-4.1-mini` por defecto, o Claude), corre un loop de **tool-calling** contra herramientas de `crm`/`catalog`, y responde por WhatsApp reusando el pipe de `conversations`. El turno NO corre en el webhook: este **encola una Cloud Task** y un endpoint interno (`POST /api/v1/bots/engine/dispatch`, OIDC) corre el turno con CPU asignada (**ADR-012**).

> **🔑 Tres cosas que distinguen este diseño del overview viejo (`docs/modules/bots.md` + ADR-005 original, 2026-05-28) — leerlas ANTES de los models** (reconciliaciones §0 de la spec):
> 1. **Async del turno = Cloud Tasks**, NO `BackgroundTasks` ni síncrono. El webhook de `conversations`, tras su pipe síncrono, llama `bots.cloud_tasks.enqueue_turn(conversation_id, mid)` (solo si `assignee_type=='bot'`). Reintentos+backoff+DLQ los da la cola. ADR-012.
> 2. **Motor = Embedded multi-proveedor**. `EmbeddedBotEngine` + adaptadores por provider (`providers/openai.py` default `gpt-4.1-mini`, `providers/claude.py`). `ExternalBotEngine` está **DISEÑADO pero DIFERIDO**: las entidades llevan `provider`/`external_webhook_url`/`external_webhook_secret_name`, pero NO se implementa el código del engine externo ni los endpoints `/engine/external/*` en el MVP.
> 3. **Mensajes en Firestore (CQRS, ADR-011), NO Postgres**. NO hay tabla `message`. `BotEvent.input_message_id`/`output_message_id` = **`varchar(255)` planos = el `mid` (doc-id Firestore)**, NO FK. El bot **lee el historial del hilo desde Firestore** (`app.core.firestore.list_message_docs`) para armar el prompt; el doc del outbound del bot lleva `bot_configuration_id`.

---

## 1. Estructura de archivos a crear

```
backend/app/
├── core/
│   └── cloud_tasks.py                     # NUEVO cross-cutting: cliente lazy Cloud Tasks + enqueue_turn (OIDC). Molde secrets.py/firestore.py  ── F3
└── modules/bots/
    ├── __init__.py
    ├── enums.py                           # BotType, BotProvider, ToolCallStatus, BotEventType  (StrEnum; NO catálogos en BD)
    ├── models/
    │   ├── __init__.py                    # importa todos los modelos + el M:N (registro en Base.metadata)
    │   ├── associations.py                # M:N bot_configuration_tool (Table, igual que admin/associations.py)
    │   ├── bot_configuration.py           # ── F1
    │   ├── bot_configuration_version.py   # ── F1
    │   ├── bot_tool.py                     # ── F2
    │   ├── conversation_bot_state.py      # ── F3
    │   ├── bot_tool_call.py               # ── F3 (traza, SIN SoftDelete)
    │   └── bot_event.py                   # ── F3 (traza, SIN SoftDelete; input/output_message_id = varchar(255) NO FK)
    ├── schemas/
    │   ├── __init__.py
    │   ├── bot_configuration.py           # Create/Update/Item/Detail/Option + ActivateVersionRequest
    │   ├── bot_configuration_version.py   # Create/Item/Detail
    │   ├── bot_tool.py                     # Create/Update/Item/Detail/Option + ConfigurationToolsUpdate (bulk M:N)
    │   ├── conversation_bot_state.py       # Item/Detail + ResetBotStateRequest
    │   ├── bot_tool_call.py               # Item
    │   ├── bot_event.py                    # Item
    │   └── engine.py                       # DispatchTurnRequest  (body de /engine/dispatch + /engine/dispatch-manual)
    ├── repositories/
    │   ├── __init__.py
    │   ├── bot_configuration.py           # get_by_code, list/active, ALLOWED_FIELDS
    │   ├── bot_configuration_version.py   # max_version, get_for_config, list_for_config
    │   ├── bot_tool.py                     # get_by_code, list/active, tool_ids_for_config, set_config_tools (bulk M:N)
    │   ├── conversation_bot_state.py       # get_by_conversation (UNIQUE)
    │   ├── bot_tool_call.py               # list_for_conversation, list_for_event
    │   └── bot_event.py                    # list_for_conversation, max_turn_number
    ├── services/
    │   ├── __init__.py
    │   ├── bot_configuration.py           # CRUD config + activate_version
    │   ├── bot_configuration_version.py   # create (max+1; valida external_webhook), get_detail
    │   ├── bot_tool.py                     # CRUD catálogo de tools + set_config_tools (bulk M:N)
    │   ├── conversation_bot_state.py       # get_state, reset_state
    │   ├── bot_event.py                    # list_events (read-only depuración)
    │   ├── bot_tool_call.py               # list_tool_calls (read-only depuración)
    │   └── engine/
    │       ├── __init__.py                 # engine_factory(version) -> BotEngine
    │       ├── base.py                     # interfaz BotEngine (dispatch_turn / choose_bot_for_conversation)
    │       ├── embedded.py                 # EmbeddedBotEngine — orquesta el turno + loop tool-calling
    │       ├── providers/
    │       │   ├── __init__.py
    │       │   ├── openai.py               # adaptador OpenAI (function calling); complete()
    │       │   └── claude.py               # adaptador Claude (tool use + prompt caching); complete()
    │       └── tools/
    │           ├── __init__.py             # TOOL_REGISTRY + @register_tool + BotInvocationContext
    │           ├── crm.py                  # resolve_or_create_contact / register_lead_note / set_lead_status
    │           └── catalog.py              # list_verticals / list_services_by_vertical / list_products_by_vertical
    └── routers/
        ├── __init__.py                     # aggregator: prefix="/bots"
        ├── bot_configuration.py           # /configurations/* (+ /versions/*, /activate-version, /tools M:N)
        ├── bot_tool.py                     # /tools/*
        ├── conversation_bot_state.py       # /conversations/{cid}/state + state/reset + events + tool-calls
        └── engine.py                       # /engine/dispatch (OIDC, sin RBAC) + /engine/dispatch-manual (RBAC)
```

> **El `engine` es un sub-paquete de `services`** (cohesión por dominio, igual que `conversations.services.webhook_processor`): el router `engine.py` solo autentica (OIDC del dispatch / RBAC del manual) y delega a `services.engine.embedded.dispatch_turn`. Un provider nuevo = un módulo nuevo en `providers/`, sin tocar el engine (despacho por `BotConfigurationVersion.provider`). Una tool nueva = un `@register_tool` en `tools/`, sin tocar el dispatcher.
> **`models/associations.py`**: `bots` SÍ introduce un M:N nuevo (`bot_configuration_tool`) → va en `associations.py` (igual que `admin/associations.py`), para que SQLAlchemy lo vea antes de los modelos que lo referencian.

### 1.1 Registro del módulo

Registrar `bots` en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean) — **lo cablea F1** (en F0 el skeleton es inerte, NO se registra):

```python
from app.modules import admin, bots, catalog, clinic, conversations, crm, staff  # noqa: F401
```

Y registrar el aggregator en `app/main.py` (F1):

```python
from app.modules.bots.routers import router as bots_router
...
app.include_router(bots_router, prefix=settings.API_V1_PREFIX)   # /api/v1/bots/...
```

> **`/engine/dispatch` es interno, NO va en un router top-level aparte** (a diferencia de `conversations.webhooks`): vive dentro del aggregator de `bots` bajo `/bots/engine/dispatch`, pero su dependencia de auth es **OIDC/shared-secret** (no `RequirePermission`), porque lo invoca Cloud Tasks (§9). El aggregator `routers/__init__.py` replica el patrón de `crm`/`conversations`:

```python
"""
Aggregates the bots sub-routers under one prefix. `main.py` includes this `router` once.
El sub-router `engine` declara endpoints internos (/engine/dispatch OIDC, /engine/dispatch-manual
RBAC) además del CRUD. Orden: configuration/tool antes que el catch-all de state por /{cid}.
"""

from fastapi import APIRouter

from app.modules.bots.routers.bot_configuration import router as bot_configuration_router
from app.modules.bots.routers.bot_tool import router as bot_tool_router
from app.modules.bots.routers.conversation_bot_state import router as state_router
from app.modules.bots.routers.engine import router as engine_router

router = APIRouter(prefix="/bots")
router.include_router(bot_configuration_router)  # /configurations/* (+ versions, activate, tools M:N)
router.include_router(bot_tool_router)           # /tools/*
router.include_router(engine_router)             # /engine/dispatch, /engine/dispatch-manual
router.include_router(state_router)              # /conversations/{cid}/state|events|tool-calls

__all__ = ["router"]
```

---

## 2. Enums — `enums.py` (en código, NO en BD)

`StrEnum` (ruff UP042) — contratos estables del código, no catálogos en BD. Las columnas que los referencian son `varchar` planas; Pydantic valida contra el enum, la BD almacena el slug. **NO se redefine `ChannelType`** (el bot no la usa directamente; las tools que tocan crm reusan `crm.enums.ChannelType`).

```python
"""
bots enums. NONE of these are DB catalogs — son value sets a nivel de código (las columnas
que los referencian son varchar plano; Pydantic valida, la BD guarda el slug). BotProvider
en el MVP solo implementa openai (default) + claude; el resto (vertex_ai/azure_openai/
external_webhook) está DISEÑADO pero el adaptador NO existe → PROVIDER_NOT_SUPPORTED en runtime.
"""

from __future__ import annotations

from enum import StrEnum


class BotType(StrEnum):
    preventa = "preventa"
    postventa = "postventa"
    general = "general"
    custom = "custom"


class BotProvider(StrEnum):
    openai = "openai"            # MVP — default (gpt-4.1-mini)
    claude = "claude"            # MVP
    vertex_ai = "vertex_ai"      # diseñado, sin adaptador en el MVP
    azure_openai = "azure_openai"  # diseñado, sin adaptador en el MVP
    external_webhook = "external_webhook"  # ExternalBotEngine DIFERIDO


class ToolCallStatus(StrEnum):
    pending = "pending"
    success = "success"
    error = "error"
    timeout = "timeout"


class BotEventType(StrEnum):
    turn_started = "turn_started"
    turn_completed = "turn_completed"
    turn_failed = "turn_failed"
    tool_dispatched = "tool_dispatched"
    handoff_triggered = "handoff_triggered"   # diseñado (handoff automático = F4 diferida)
```

> **`BotProvider.external_webhook`** existe en el enum (las entidades lo aceptan, y `BotConfigurationVersion` valida `external_webhook_url`), pero el **engine externo NO se implementa** en el MVP: `engine_factory` levanta `PROVIDER_NOT_SUPPORTED` (400) para cualquier provider sin adaptador (`vertex_ai`/`azure_openai`/`external_webhook`). Es la materialización de "ExternalBotEngine DISEÑADO pero DIFERIDO" (reconciliación §0.2).

---

## 3. Models — SQLAlchemy 2.0

> ⚠ **`input_message_id`/`output_message_id` de `BotEvent` son `mapped_column(String(255), nullable=True)` SIN `ForeignKey`.** NO hay tabla `message` (el stream vive en Firestore, ADR-011) — son el `mid` (doc-id Firestore = wamid inbound / uuid outbound) en texto plano. Declarar un FK rompería el mapper (no existe la tabla destino). El bot lee el contenido del mensaje desde Firestore (`firestore.list_message_docs`), no desde Postgres.
> ⚠ **FKs reales** (`bot_configuration.id`, `bot_configuration_version.id`, `bot_tool.id`, `bot_event.id`, `conversation.id`) SÍ llevan `ForeignKey(...)` — esas tablas existen (las de `bots` se crean en 0017–0019; `conversation` ya existe desde `conversations` 0016).
> ⚠ **forward FK inversa**: las columnas `channel_account.bot_configuration_id` y `conversation.bot_configuration_id` (declaradas en `conversations` como `varchar(36)` sin constraint, ADR-009) reciben su **`ALTER TABLE ADD CONSTRAINT`** en la migración `0017` de `bots` (Postgres-only; §8). `bots` NO declara un `relationship` inverso (consistente con "sin relationship cross-módulo" de crm/conversations — acceso por id + batch maps).
> ⚠ **UNIQUE parciales dialect-agnósticos** (`code` vivo): `Index(..., unique=True, postgresql_where=text("deleted_at IS NULL"), sqlite_where=text("deleted_at IS NULL"))` — el `sqlite_where` espeja el `postgresql_where` para que el smoke (`create_all`) reproduzca el índice parcial (patrón real de `crm.lead_status`/`conversations.channel_account`).
> ⚠ **JSONB variant**: `parameters`/`parameters_schema`/`collected_slots`/`arguments`/`result`/`metadata` usan `JSON().with_variant(JSONB(), "postgresql")`.

### `models/bot_configuration.py` — tabla `bot_configuration` — PK·A·SD·T

```python
"""
BotConfiguration = un bot configurable de la clínica (preventa, postventa_dental, ...). Es
el contenedor; el comportamiento concreto (prompt/provider/model/params) vive en sus
BotConfigurationVersion (versionado inmutable). current_version_id apunta a la versión
VIGENTE (NULL = sin versión → no usable: activate/dispatch dan NO_CURRENT_VERSION). FK real
a bot_configuration_version (forward dentro del mismo módulo: la columna se crea en 0017 y la
FK se agrega tras crear bot_configuration_version, también en 0017 — ver §12).
max_turns_per_conversation (nullable) = guard opcional de costo (None = sin límite).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class BotConfiguration(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "bot_configuration"
    __table_args__ = (
        # Partial UNIQUE: un `code` VIVO es único (single-tenant). Tras soft-delete libera el slug.
        Index(
            "uq_bot_configuration_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)       # slug: preventa, postventa_dental
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bot_type: Mapped[str] = mapped_column(String(20), nullable=False)   # BotType
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Versión vigente. FK real → bot_configuration_version (se agrega tras crear esa tabla,
    # misma migración 0017). NULL = sin versión activa (no usable).
    current_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bot_configuration_version.id"), nullable=True, index=True
    )
    # Guard opcional de costo: máximo de turnos del bot por conversación (None = sin límite).
    max_turns_per_conversation: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

### `models/bot_configuration_version.py` — tabla `bot_configuration_version` — PK·A·SD·T

```python
"""
BotConfigurationVersion = una versión INMUTABLE del comportamiento de un bot (prompt +
provider + model + params + tools-via-M:N del bot). Editar el prompt/params = crear una
NUEVA versión (no in-place); la promoción se hace con activate-version (setea
bot_configuration.current_version_id). UNIQUE (bot_configuration_id, version); el service
asigna max+1. provider/external_webhook_* soportan el ExternalBotEngine DIFERIDO (campos
presentes, sin impl). is_active = soft-disable de la versión (distinto de "ser la current").
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class BotConfigurationVersion(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "bot_configuration_version"
    __table_args__ = (
        # Un número de versión es único por bot. NO parcial: las versiones no se soft-deletean
        # de forma que liberen el número (son inmutables; is_active solo las deshabilita).
        Index(
            "uq_bot_config_version_number",
            "bot_configuration_id",
            "version",
            unique=True,
        ),
    )

    bot_configuration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)        # service asigna max+1
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)    # BotProvider
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)  # default gpt-4.1-mini (lo pone el schema)
    # {temperature?, max_tokens?, top_p?, ...} — schema libre por provider.
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    # Solo provider='external_webhook' (DIFERIDO). url requerida en ese caso (validación service).
    external_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_webhook_secret_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)        # changelog del prompt
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
```

> **`is_active` vs `current`**: `is_active` (columna propia de la versión) es un soft-disable a nivel versión; ser la **current** es que `bot_configuration.current_version_id` apunte a ella. Son ortogonales: una versión puede estar `is_active=true` y NO ser la current (es candidata a activar), o ser la current (en uso). `ActiveMixin.active` se reusa como ese `is_active` semántico → en código se lee `version.active`; la spec lo nombra `is_active` para el contrato. **Decisión**: se usa el `ActiveMixin.active` heredado como el `is_active` de la spec (no se agrega una segunda columna `is_active`) — ver `deviations`.

### `models/bot_tool.py` — tabla `bot_tool` — PK·A·SD·T

```python
"""
BotTool = catálogo CONFIGURABLE de herramientas que un bot puede invocar (function calling /
tool use). target_service = '<module>.<service>.<function>' resuelto por TOOL_REGISTRY en
runtime (si el code no está registrado → TOOL_NOT_REGISTERED 404 en runtime, NO al boot —
permite seedear tools cuyo target aún no existe, ej. scheduling.* diferido). parameters_schema
= JSON Schema (subset común OpenAI/Anthropic). requires_confirmation = la tool muta algo
sensible (ej. set_lead_status) → el engine puede pedir confirmación (hardening; en el MVP se
loguea y se ejecuta). El M:N bot_configuration_tool decide qué tools ve cada bot.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class BotTool(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "bot_tool"
    __table_args__ = (
        Index(
            "uq_bot_tool_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(60), nullable=False)         # list_verticals, set_lead_status
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)        # la lee el LLM para decidir cuándo invocar
    parameters_schema: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    target_service: Mapped[str] = mapped_column(String(120), nullable=False)  # module.service.function
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # is_active de la spec = ActiveMixin.active (soft-disable de la tool).
```

### `models/conversation_bot_state.py` — tabla `conversation_bot_state` — PK·A·SD·T

```python
"""
ConversationBotState = el estado de la sesión del bot en UNA conversación (slots
recolectados, intent actual, contador de turnos, versión con la que arrancó). UNIQUE
conversation_id (un solo estado por hilo). bot_configuration_version_id congela la versión
con la que el hilo viene operando (NO se migra al promover otra versión; reset explícito vía
/state/reset). FK real a conversation (existe) + bot_configuration + bot_configuration_version.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class ConversationBotState(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "conversation_bot_state"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, unique=True, index=True
    )
    bot_configuration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration.id"), nullable=False, index=True
    )
    bot_configuration_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration_version.id"), nullable=False, index=True
    )
    current_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    collected_slots: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    last_node: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_bot_turn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
```

### `models/bot_tool_call.py` — tabla `bot_tool_call` — PK·A·T (SIN SoftDelete — traza)

```python
"""
BotToolCall = traza INMUTABLE de una invocación de tool dentro de un turno (args + result +
status + latencia). SIN SoftDeleteMixin. tool_use_id = el id del tool_use del LLM (para
matchear cuando el modelo pide varias tools en una vuelta). bot_event_id (nullable) la ata al
turno (BotEvent). FK reales a conversation/bot_event/bot_tool.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class BotToolCall(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "bot_tool_call"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    bot_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bot_event.id"), nullable=True, index=True
    )
    bot_tool_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_tool.id"), nullable=False, index=True
    )
    tool_use_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)      # ToolCallStatus
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

### `models/bot_event.py` — tabla `bot_event` — PK·A·T (SIN SoftDelete — traza)

```python
"""
BotEvent = traza INMUTABLE de UN turno del bot (start/complete/fail + tokens/costo/latencia).
SIN SoftDeleteMixin. UNIQUE (conversation_id, turn_number). input_message_id/output_message_id
son el `mid` (doc-id Firestore: wamid inbound / uuid outbound del send_bot_outbound) en
VARCHAR(255) PLANO — NO FK (no hay tabla message; ADR-011). FK reales a conversation/
bot_configuration/bot_configuration_version. metadata = raw response/fingerprint del provider.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class BotEvent(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "bot_event"
    __table_args__ = (
        Index("uq_bot_event_conversation_turn", "conversation_id", "turn_number", unique=True),
        Index("ix_bot_event_config_created", "bot_configuration_id", "created_on"),
        Index("ix_bot_event_type_created", "event_type", "created_on"),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    bot_configuration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration.id"), nullable=False
    )
    bot_configuration_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration_version.id"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # BotEventType
    # 🔑 el `mid` (doc-id Firestore) del inbound/outbound — NO FK (no hay tabla message; ADR-011).
    input_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimated_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
```

> **`metadata` es palabra reservada de SQLAlchemy Declarative** (`Base.metadata`) → el atributo Python se llama `event_metadata` y la **columna** se nombra explícitamente `"metadata"` (`mapped_column("metadata", ...)`). El schema Pydantic expone `metadata` (alias). Ver `deviations`.

### `models/associations.py` — M:N `bot_configuration_tool`

```python
"""
M:N entre BotConfiguration y BotTool: qué tools puede invocar cada bot. PK compuesta. Igual
patrón que admin/associations.py (Table en un solo archivo para que SQLAlchemy lo vea antes de
los modelos). ondelete CASCADE: borrar (hard) un bot/tool limpia las filas del M:N; el borrado
de negocio es soft-delete (deleted_at) en las entidades, no toca esta tabla.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

bot_configuration_tool = Table(
    "bot_configuration_tool",
    Base.metadata,
    Column(
        "bot_configuration_id",
        String(36),
        ForeignKey("bot_configuration.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "bot_tool_id",
        String(36),
        ForeignKey("bot_tool.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
```

### `models/__init__.py`

```python
"""
Importar los modelos acá los registra en Base.metadata antes de que Alembic lea el schema y de
que se resuelvan los relationship() por string. Orden: associations + padres (bot_configuration,
bot_tool) antes que hijos (version, state, tool_call, event). NB: bot_event.input/output_message_id
NO son FK (el stream de mensajes vive en Firestore, ADR-011).
"""

from app.modules.bots.models.associations import bot_configuration_tool
from app.modules.bots.models.bot_configuration import BotConfiguration
from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion
from app.modules.bots.models.bot_tool import BotTool
from app.modules.bots.models.conversation_bot_state import ConversationBotState
from app.modules.bots.models.bot_event import BotEvent
from app.modules.bots.models.bot_tool_call import BotToolCall

__all__ = [
    "bot_configuration_tool",
    "BotConfiguration",
    "BotConfigurationVersion",
    "BotTool",
    "ConversationBotState",
    "BotEvent",
    "BotToolCall",
]
```

> **Lazy strategy**: NO se declaran `relationship(...)` cross-módulo (a `Conversation`/`User`) — patrón crm/conversations "sin relationship cross-módulo, todo por FK column + batch maps". Dentro del módulo, el M:N de tools de un bot se resuelve por una query de repo (`tool_ids_for_config`) en vez de un `relationship(secondary=...)` lazy (lectura explícita, sin N+1 silencioso; el editor de tools de la UI no necesita el grafo cargado). El `BotConfiguration.versions` (lista de versiones) tampoco se modela como relationship: se lista por `bot_configuration_version_repository.list_for_config`.

---

## 4. Schemas Pydantic v2 — completos

> ⚠ **Convenciones** (idénticas a crm/conversations): (1) no usar Ellipsis (`...`) en `Field(...)`; (2) `Annotated` solo para `Query`/`Path` en routers; (3) validators `@field_validator` single-field, `@model_validator(mode="after")` cross-field; (4) mensajes de validator en inglés (422); copy user-facing en español en el Zod del front; (5) `model_config = ConfigDict(from_attributes=True)` en `*Item`/`*Detail`/`*Option`.

### `schemas/bot_configuration.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.enums import BotType


class BotConfigurationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    bot_type: BotType
    description: str | None = Field(default=None, max_length=4000)
    max_turns_per_conversation: int | None = Field(default=None, ge=1, le=1000)


class BotConfigurationUpdate(BaseModel):
    """Partial. `code` editable (re-dispara el guard de unicidad). El comportamiento
    (prompt/provider/model) NO se toca acá — eso es una NUEVA versión."""

    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    bot_type: BotType | None = None
    description: str | None = Field(default=None, max_length=4000)
    max_turns_per_conversation: int | None = Field(default=None, ge=1, le=1000)
    active: bool | None = None


class BotConfigurationOption(BaseModel):
    """Dropdown — GET /configurations/active (raw list). Lo consume el editor de canales
    (asociar un bot a un ChannelAccount) y la depuración."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    bot_type: BotType


class BotConfigurationItem(BaseModel):
    """Row de la tabla /configurations/list."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    bot_type: BotType
    description: str | None
    current_version_id: str | None
    current_version_number: int | None = None   # denormalizado (lookup de la versión vigente)
    max_turns_per_conversation: int | None
    version_count: int = 0                       # denormalizado (cuántas versiones tiene)
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class BotConfigurationDetail(BotConfigurationItem):
    """Full para el drawer + tab de versiones. Incluye la versión vigente expandida (si la hay)
    y el listado liviano de versiones (la lista completa con prompt se trae por /versions)."""

    current_version: "BotConfigurationVersionItem | None" = None
    tool_ids: list[str] = Field(default_factory=list)   # ids de bot_tool asociados (M:N)


class ActivateVersionRequest(BaseModel):
    """Body OPCIONAL de POST /configurations/{id}/activate-version/{vid}. El vid va en la URL;
    el body queda para futuros flags (ej. reset de estados en curso). Hoy vacío."""

    pass


# late import para el forward ref de current_version
from app.modules.bots.schemas.bot_configuration_version import (  # noqa: E402
    BotConfigurationVersionItem,
)

BotConfigurationDetail.model_rebuild()
```

> **`code` único vivo**: `create`/`update` chequean `get_by_code` antes → `BOT_CONFIGURATION_CODE_TAKEN` (409). `current_version_number`/`version_count` son **denormalizados** (lookup batch en el service) → NO van en `ALLOWED_FIELDS`.

### `schemas/bot_configuration_version.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.enums import BotProvider

DEFAULT_MODEL = "gpt-4.1-mini"   # default OpenAI (reconciliación §0.2)


class BotConfigurationVersionCreate(BaseModel):
    """Crear una NUEVA versión de un bot (no se edita in-place). El número de versión lo
    asigna el service (max+1). provider='external_webhook' ⇒ external_webhook_url requerida."""

    system_prompt: str = Field(min_length=1, max_length=20000)
    provider: BotProvider = BotProvider.openai
    model_name: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    external_webhook_url: str | None = Field(default=None, max_length=500)
    external_webhook_secret_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _external_webhook_requires_url(self) -> "BotConfigurationVersionCreate":
        # Validación de FORMA (422). El service repite la regla como BadRequestException 400
        # (EXTERNAL_WEBHOOK_URL_REQUIRED) para tener el `code` en el contrato.
        if self.provider == BotProvider.external_webhook and not self.external_webhook_url:
            raise ValueError("external_webhook_url is required when provider is external_webhook")
        return self


class BotConfigurationVersionItem(BaseModel):
    """Row liviano (lista de versiones; NO incluye el system_prompt completo en la tabla)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    bot_configuration_id: str
    version: int
    provider: BotProvider
    model_name: str
    is_active: bool                          # = active (ver §3 deviation)
    is_current: bool = False                 # denormalizado: id == bot_configuration.current_version_id
    notes: str | None
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None


class BotConfigurationVersionDetail(BotConfigurationVersionItem):
    """Full (editor de versión / preview): incluye el prompt y los params."""

    system_prompt: str
    parameters: dict[str, Any]
    external_webhook_url: str | None
    external_webhook_secret_name: str | None   # NO expone el secreto, solo su NOMBRE (resuelve secrets.resolve)
```

### `schemas/bot_tool.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo


class BotToolCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)   # JSON Schema (subset común)
    target_service: str = Field(min_length=1, max_length=120)         # module.service.function
    requires_confirmation: bool = False


class BotToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    parameters_schema: dict[str, Any] | None = None
    target_service: str | None = Field(default=None, min_length=1, max_length=120)
    requires_confirmation: bool | None = None
    active: bool | None = None
    # `code` NO editable tras crear (es la clave que cruza con TOOL_REGISTRY).


class BotToolOption(BaseModel):
    """Dropdown / multiselect del editor de tools por bot."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    requires_confirmation: bool


class BotToolItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str
    target_service: str
    requires_confirmation: bool
    is_registered: bool = False    # denormalizado: target_service ∈ TOOL_REGISTRY (lo computa el service)
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class BotToolDetail(BotToolItem):
    parameters_schema: dict[str, Any]


class ConfigurationToolsUpdate(BaseModel):
    """Body de PUT /configurations/{id}/tools — set bulk del M:N (reemplaza el conjunto)."""

    tool_ids: list[str] = Field(default_factory=list)
```

> **`is_registered`** = el `target_service` de la tool está en `TOOL_REGISTRY` (computado por el service contra el registry en memoria). La UI lo muestra como un badge "registrada / no registrada" — útil para ver que las tools de scheduling (diferidas) quedan **no registradas** hasta #7 (su dispatch daría `TOOL_NOT_REGISTERED`). NO es columna → NO va en `ALLOWED_FIELDS`.

### `schemas/conversation_bot_state.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationBotStateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    bot_configuration_id: str
    bot_configuration_version_id: str
    bot_configuration_code: str | None = None     # denormalizado (depuración)
    version_number: int | None = None             # denormalizado
    current_intent: str | None
    collected_slots: dict[str, Any] = Field(default_factory=dict)
    last_node: str | None
    last_bot_turn_at: datetime | None
    turn_count: int
    active: bool
    created_on: datetime
    updated_on: datetime


class ConversationBotStateDetail(ConversationBotStateItem):
    """Para el panel de depuración: igual que Item por ahora (la timeline de eventos y las tool
    calls se traen por sus propios endpoints)."""

    pass


class ResetBotStateRequest(BaseModel):
    """Body de POST /conversations/{cid}/state/reset. Limpia slots/intent/turn_count y re-fija
    la versión vigente del bot. `keep_assignment` (default true) = no cambia el assignee del
    hilo (sigue siendo bot); false = solo resetea el estado del bot (handoff lo maneja
    conversations)."""

    reason: str | None = Field(default=None, max_length=255)
```

### `schemas/bot_tool_call.py` / `schemas/bot_event.py`

```python
# schemas/bot_tool_call.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.bots.enums import ToolCallStatus


class BotToolCallItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    bot_event_id: str | None
    bot_tool_id: str
    bot_tool_code: str | None = None       # denormalizado (depuración)
    tool_use_id: str | None
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    status: ToolCallStatus
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    latency_ms: int | None
    created_on: datetime
```

```python
# schemas/bot_event.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BotEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    bot_configuration_id: str
    bot_configuration_version_id: str
    turn_number: int
    event_type: str
    input_message_id: str | None      # mid Firestore (NO FK)
    output_message_id: str | None
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    cost_estimated_usd: Decimal | None
    error: str | None
    # El atributo del modelo es `event_metadata` (col "metadata"); se expone como `metadata`.
    metadata: dict[str, Any] | None = Field(default=None, alias="event_metadata")
    created_on: datetime
```

### `schemas/engine.py`

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class DispatchTurnRequest(BaseModel):
    """Body de POST /engine/dispatch (target de Cloud Tasks, OIDC) y de
    POST /engine/dispatch-manual (RBAC, debugging). input_message_id = el `mid` (doc-id
    Firestore) del inbound que disparó el turno (opcional: en el dispatch manual no hay un
    mensaje nuevo, el engine toma el último inbound del hilo desde Firestore)."""

    conversation_id: str = Field(min_length=1, max_length=36)
    input_message_id: str | None = Field(default=None, max_length=255)
```

---

## 5. Repositories

`ALLOWED_FIELDS` = whitelist de columnas filtrable/ordenable. Solo columnas **reales** (lección hotfix `cd10c78`); los denormalizados (`current_version_number`, `version_count`, `is_registered`, etc.) NO. `defaultSort` de configurations = `created_on desc` (spec §6).

### `repositories/bot_configuration.py`

```python
class BotConfigurationRepository(BaseRepository[BotConfiguration]):
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "bot_type", "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(BotConfiguration)

    async def get_by_code(self, db, code: str) -> BotConfiguration | None:
        """Resuelve el bot VIVO por code. Respalda el guard 409 BOT_CONFIGURATION_CODE_TAKEN."""
        result = await db.execute(
            select(BotConfiguration).where(
                BotConfiguration.code == code,
                BotConfiguration.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list_active(self, db) -> list[BotConfiguration]:
        result = await db.execute(
            select(BotConfiguration)
            .where(BotConfiguration.active.is_(True), BotConfiguration.deleted_at.is_(None))
            .order_by(BotConfiguration.name.asc())
        )
        return list(result.scalars().all())


bot_configuration_repository = BotConfigurationRepository()
```

### `repositories/bot_configuration_version.py`

```python
class BotConfigurationVersionRepository(BaseRepository[BotConfigurationVersion]):
    ALLOWED_FIELDS: set[str] = {"version", "provider", "active", "created_on"}

    def __init__(self) -> None:
        super().__init__(BotConfigurationVersion)

    async def max_version(self, db, bot_configuration_id: str) -> int:
        """El número de versión más alto del bot (0 si no tiene). El service asigna max+1."""
        result = await db.execute(
            select(func.coalesce(func.max(BotConfigurationVersion.version), 0)).where(
                BotConfigurationVersion.bot_configuration_id == bot_configuration_id,
                BotConfigurationVersion.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def list_for_config(self, db, bot_configuration_id: str) -> list[BotConfigurationVersion]:
        result = await db.execute(
            select(BotConfigurationVersion)
            .where(
                BotConfigurationVersion.bot_configuration_id == bot_configuration_id,
                BotConfigurationVersion.deleted_at.is_(None),
            )
            .order_by(BotConfigurationVersion.version.desc())
        )
        return list(result.scalars().all())

    async def version_count_map(self, db, config_ids: list[str]) -> dict[str, int]:
        """config_id → nº de versiones vivas (batch, para BotConfigurationItem.version_count)."""
        if not config_ids:
            return {}
        result = await db.execute(
            select(
                BotConfigurationVersion.bot_configuration_id,
                func.count(BotConfigurationVersion.id),
            )
            .where(
                BotConfigurationVersion.bot_configuration_id.in_(config_ids),
                BotConfigurationVersion.deleted_at.is_(None),
            )
            .group_by(BotConfigurationVersion.bot_configuration_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}


bot_configuration_version_repository = BotConfigurationVersionRepository()
```

### `repositories/bot_tool.py` (incl. el bulk M:N)

```python
class BotToolRepository(BaseRepository[BotTool]):
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "target_service", "requires_confirmation", "active",
        "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(BotTool)

    async def get_by_code(self, db, code: str) -> BotTool | None:
        result = await db.execute(
            select(BotTool).where(BotTool.code == code, BotTool.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db) -> list[BotTool]:
        result = await db.execute(
            select(BotTool)
            .where(BotTool.active.is_(True), BotTool.deleted_at.is_(None))
            .order_by(BotTool.name.asc())
        )
        return list(result.scalars().all())

    async def tool_ids_for_config(self, db, bot_configuration_id: str) -> list[str]:
        """Los bot_tool_id asociados a un bot (lee el M:N directamente, sin relationship)."""
        result = await db.execute(
            select(bot_configuration_tool.c.bot_tool_id).where(
                bot_configuration_tool.c.bot_configuration_id == bot_configuration_id
            )
        )
        return [row[0] for row in result.all()]

    async def active_tools_for_config(self, db, bot_configuration_id: str) -> list[BotTool]:
        """Las BotTool VIVAS y activas de un bot (las que ve el engine al armar el prompt).
        JOIN M:N + filtro active/deleted_at."""
        result = await db.execute(
            select(BotTool)
            .join(
                bot_configuration_tool,
                bot_configuration_tool.c.bot_tool_id == BotTool.id,
            )
            .where(
                bot_configuration_tool.c.bot_configuration_id == bot_configuration_id,
                BotTool.active.is_(True),
                BotTool.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def set_config_tools(self, db, bot_configuration_id: str, tool_ids: list[str]) -> None:
        """Reemplaza el conjunto de tools del bot (delete-all + insert; misma tx). Molde del
        editor de matriz de crm. NO valida existencia acá — el service valida que los tool_ids
        existan (BOT_TOOL_NOT_FOUND) antes de llamar."""
        await db.execute(
            delete(bot_configuration_tool).where(
                bot_configuration_tool.c.bot_configuration_id == bot_configuration_id
            )
        )
        for tid in dict.fromkeys(tool_ids):   # dedup preservando orden
            await db.execute(
                insert(bot_configuration_tool).values(
                    bot_configuration_id=bot_configuration_id, bot_tool_id=tid
                )
            )


bot_tool_repository = BotToolRepository()
```

### `repositories/conversation_bot_state.py` / `bot_event.py` / `bot_tool_call.py`

```python
class ConversationBotStateRepository(BaseRepository[ConversationBotState]):
    ALLOWED_FIELDS: set[str] = set()   # consultado por conversation_id (UNIQUE)

    def __init__(self) -> None:
        super().__init__(ConversationBotState)

    async def get_by_conversation(self, db, conversation_id: str) -> ConversationBotState | None:
        result = await db.execute(
            select(ConversationBotState).where(
                ConversationBotState.conversation_id == conversation_id,
                ConversationBotState.deleted_at.is_(None),
            )
        )
        return result.scalars().first()


class BotEventRepository(BaseRepository[BotEvent]):
    ALLOWED_FIELDS: set[str] = set()   # leído por conversation_id (timeline de depuración)

    def __init__(self) -> None:
        super().__init__(BotEvent)

    async def max_turn_number(self, db, conversation_id: str) -> int:
        result = await db.execute(
            select(func.coalesce(func.max(BotEvent.turn_number), 0)).where(
                BotEvent.conversation_id == conversation_id
            )
        )
        return int(result.scalar_one())

    async def list_for_conversation(self, db, conversation_id: str) -> list[BotEvent]:
        result = await db.execute(
            select(BotEvent)
            .where(BotEvent.conversation_id == conversation_id)
            .order_by(BotEvent.turn_number.asc(), BotEvent.created_on.asc())
        )
        return list(result.scalars().all())


class BotToolCallRepository(BaseRepository[BotToolCall]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(BotToolCall)

    async def list_for_conversation(self, db, conversation_id: str) -> list[BotToolCall]:
        result = await db.execute(
            select(BotToolCall)
            .where(BotToolCall.conversation_id == conversation_id)
            .order_by(BotToolCall.started_at.asc())
        )
        return list(result.scalars().all())
```

> **`BotEvent`/`BotToolCall`/`ConversationBotState` no se paginan ni filtran desde el front** (`ALLOWED_FIELDS = set()`): se leen por `conversation_id` para el panel de depuración (read-only). La timeline de un hilo es acotada (turnos del bot); no necesita paginación dinámica. **Denorm sin N+1**: `bot_configuration_code` / `bot_tool_code` / `version_number` se resuelven con un batch lookup por ids en el service (mismo patrón que crm/conversations).

---

## 6. Services (módulos de funciones)

CRUD estándar (molde `catalog.vertical`/`crm.lead_status`): `list_paginated`, `create` (guard unicidad), `get_by_id`, `update`, `soft_delete`, `list_active`. Lo específico de `bots`:

### `services/bot_configuration_version.py` — `create` (max+1) + validación external

```python
async def create(
    db, bot_configuration_id: str, payload: BotConfigurationVersionCreate, *, actor_id: str
) -> SingleResponse[BotConfigurationVersionDetail]:
    """Crea una NUEVA versión (no edita in-place). Asigna version = max+1. Valida
    external_webhook. NO la activa (la activación es explícita vía activate-version)."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    if payload.provider == BotProvider.external_webhook and not payload.external_webhook_url:
        raise BadRequestException(
            "Se requiere la URL del webhook externo para el proveedor external_webhook",
            code="EXTERNAL_WEBHOOK_URL_REQUIRED",
        )
    next_version = await bot_configuration_version_repository.max_version(db, bot_configuration_id) + 1
    now = utc_now()
    version = BotConfigurationVersion(
        id=generate_uuid(), bot_configuration_id=bot_configuration_id, version=next_version,
        system_prompt=payload.system_prompt, provider=payload.provider.value,
        model_name=payload.model_name, parameters=payload.parameters,
        external_webhook_url=payload.external_webhook_url,
        external_webhook_secret_name=payload.external_webhook_secret_name,
        notes=payload.notes, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(version); await db.flush()
    # Si el bot no tiene versión vigente todavía, esta queda como current automáticamente
    # (primera versión = usable sin un activate-version extra). Decisión de UX (ver deviations).
    if config.current_version_id is None:
        config.current_version_id = version.id
        config.updated_by = actor_id; config.updated_on = now
    await db.flush()
    return await get_detail(db, version.id)   # reload + audit users + is_current
```

### `services/bot_configuration.py` — `activate_version`

```python
async def activate_version(
    db, bot_configuration_id: str, version_id: str, *, actor_id: str
) -> SingleResponse[BotConfigurationDetail]:
    """Promueve una versión a vigente (current_version_id = version_id). Valida que la versión
    EXISTA y PERTENEZCA al bot. NO migra los ConversationBotState en curso (siguen con la
    versión con la que arrancaron; reset explícito vía /state/reset — decisión spec §2)."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    version = await bot_configuration_version_repository.get_by_id(db, version_id)
    if version is None:
        raise NotFoundException("Versión no encontrada", code="BOT_VERSION_NOT_FOUND")
    if version.bot_configuration_id != bot_configuration_id:
        raise BadRequestException("La versión no pertenece a este bot", code="BOT_VERSION_NOT_OWNED")
    config.current_version_id = version.id
    config.updated_by = actor_id; config.updated_on = utc_now()
    await db.flush()
    return await get_detail(db, config.id)
```

### `services/bot_tool.py` — `set_config_tools` (bulk M:N)

```python
async def set_config_tools(
    db, bot_configuration_id: str, payload: ConfigurationToolsUpdate, *, actor_id: str
) -> SingleResponse[BotConfigurationDetail]:
    """Reemplaza el conjunto de tools del bot. Valida que el bot exista + que TODOS los
    tool_ids existan (BOT_TOOL_NOT_FOUND si alguno no). Molde del editor de matriz de crm."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    for tid in payload.tool_ids:
        if await bot_tool_repository.get_by_id(db, tid) is None:
            raise NotFoundException(f"Tool no encontrada: {tid}", code="BOT_TOOL_NOT_FOUND")
    await bot_tool_repository.set_config_tools(db, bot_configuration_id, payload.tool_ids)
    config.updated_by = actor_id; config.updated_on = utc_now()
    await db.flush()
    return await bot_configuration_service.get_detail(db, config.id)
```

### `services/conversation_bot_state.py` — `get_state` / `reset_state`

```python
async def get_state(db, conversation_id: str) -> SingleResponse[ConversationBotStateDetail]:
    state = await conversation_bot_state_repository.get_by_conversation(db, conversation_id)
    if state is None:
        raise NotFoundException("El bot no tiene estado en esta conversación", code="BOT_STATE_NOT_FOUND")
    return SingleResponse(data=await _to_detail(db, state))


async def reset_state(
    db, conversation_id: str, payload: ResetBotStateRequest, *, actor_id: str
) -> SingleResponse[ConversationBotStateDetail]:
    """Resetea slots/intent/turn_count y re-fija la versión vigente del bot (para que el hilo
    salte a la última versión tras un activate-version). NO toca el assignee del hilo (eso es
    de conversations). 404 si el hilo no tiene estado de bot."""
    state = await conversation_bot_state_repository.get_by_conversation(db, conversation_id)
    if state is None:
        raise NotFoundException("El bot no tiene estado en esta conversación", code="BOT_STATE_NOT_FOUND")
    config = await bot_configuration_repository.get_by_id(db, state.bot_configuration_id)
    state.collected_slots = {}
    state.current_intent = None
    state.last_node = None
    state.turn_count = 0
    if config is not None and config.current_version_id is not None:
        state.bot_configuration_version_id = config.current_version_id   # salta a la versión vigente
    state.updated_by = actor_id; state.updated_on = utc_now()
    await db.flush()
    return SingleResponse(data=await _to_detail(db, state))
```

---

## 6-bis. Engine package — `services/engine/` (ADR-005)

> El corazón del módulo. Orquesta el turno: arma el prompt (system + historial Firestore + tools), llama al LLM vía el adaptador del provider, corre el **loop de tool-calling** (≤ `MAX_TOOL_ITERATIONS_PER_TURN`), responde por WhatsApp reusando `conversations.message.send_bot_outbound`, y escribe las trazas (`BotEvent`/`BotToolCall`) + actualiza `ConversationBotState`.

### `engine/base.py` — interfaz `BotEngine`

```python
"""
Interfaz del motor de bots (ADR-005). El motor es agnóstico al provider del LLM; las
implementaciones concretas (EmbeddedBotEngine en el MVP; ExternalBotEngine DIFERIDO) corren un
turno completo de una conversación.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_configuration import BotConfiguration
from app.modules.conversations.models.conversation import Conversation


class BotEngine(ABC):
    @abstractmethod
    async def dispatch_turn(
        self, db: AsyncSession, *, conversation_id: str, input_message_id: str | None
    ) -> None:
        """Corre UN turno del bot sobre la conversación. Lee el historial del hilo (Firestore),
        llama al LLM, ejecuta tools, responde (send_bot_outbound) y persiste las trazas. NO
        lanza 5xx salvo para forzar el reintento de Cloud Tasks (los errores de provider se
        capturan → BotEvent(turn_failed) + mensaje de fallback)."""
        ...


async def choose_bot_for_conversation(
    db: AsyncSession, conversation: Conversation
) -> BotConfiguration | None:
    """MVP: el bot efectivo es el de la conversación (conversation.bot_configuration_id, que el
    hook de find_or_create_open setea desde channel_account.bot_configuration_id). Futuro: ruteo
    preventa/postventa por crm.PersonCustomerStatus. None si el hilo no tiene bot configurado."""
    if conversation.bot_configuration_id is None:
        return None
    return await bot_configuration_repository.get_by_id(db, conversation.bot_configuration_id)
```

### `engine/__init__.py` — `engine_factory`

```python
"""
engine_factory: elige la implementación de BotEngine según el provider de la versión vigente.
MVP: openai/claude → EmbeddedBotEngine (multi-proveedor, despacha al adaptador interno).
external_webhook → ExternalBotEngine DIFERIDO → PROVIDER_NOT_SUPPORTED (400). vertex_ai/
azure_openai → idem (sin adaptador en el MVP).
"""

from __future__ import annotations

from app.core.exceptions import BadRequestException
from app.modules.bots.enums import BotProvider
from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion
from app.modules.bots.services.engine.base import BotEngine
from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

_EMBEDDED_PROVIDERS = {BotProvider.openai, BotProvider.claude}


def engine_factory(version: BotConfigurationVersion) -> BotEngine:
    provider = BotProvider(version.provider)
    if provider in _EMBEDDED_PROVIDERS:
        return EmbeddedBotEngine()
    # external_webhook / vertex_ai / azure_openai: diseñados, sin adaptador en el MVP.
    raise BadRequestException(
        f"El proveedor '{provider.value}' no está soportado en esta versión",
        code="PROVIDER_NOT_SUPPORTED",
    )
```

### `engine/providers/` — adaptadores por provider (contrato común `complete()`)

```python
# engine/providers/openai.py
"""
Adaptador OpenAI (function calling). Contrato común complete(): mapea las BotTool a la forma
de `tools` del SDK (type=function, function={name, description, parameters}=parameters_schema)
y devuelve {text, tool_calls[], tokens_in, tokens_out, raw}. Credenciales: Settings.OPENAI_API_KEY
(global por entorno, reconciliación §0.7). Dep runtime: openai>=1.x.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderToolCall:
    tool_use_id: str            # id que devuelve el LLM para matchear el resultado
    name: str                   # = BotTool.code
    arguments: dict[str, Any]


@dataclass
class ProviderResult:
    text: str | None            # respuesta en texto (si el modelo respondió al usuario)
    tool_calls: list[ProviderToolCall]   # vacío = no pidió tools → fin del loop
    tokens_in: int | None
    tokens_out: int | None
    raw: dict[str, Any]         # raw response/fingerprint → BotEvent.metadata


class OpenAIProvider:
    async def complete(
        self, *, system: str, messages: list[dict], tools: list[dict], params: dict
    ) -> ProviderResult:
        """messages = historial mapeado a {role, content} (+ los tool results de la vuelta
        previa); tools = JSON Schema común mapeado a la forma de OpenAI. params = temperature/
        max_tokens/top_p de version.parameters. Usa AsyncOpenAI(api_key=settings.OPENAI_API_KEY).
        Mapea response.choices[0].message.tool_calls → ProviderToolCall; usage → tokens_*."""
        ...
```

```python
# engine/providers/claude.py
"""
Adaptador Claude (Anthropic tool use). Mismo contrato complete(). Mapea las BotTool a
`tools=[{name, description, input_schema}]` y el system_prompt va en `system` (con prompt
CACHING: cache_control en el bloque de system para abaratar turnos repetidos). Devuelve
ProviderResult (content blocks type=text → text; type=tool_use → ProviderToolCall; usage →
tokens_*). Credenciales: Settings.ANTHROPIC_API_KEY. Dep runtime: anthropic>=0.40 (ya está por
conversations). El subset de JSON Schema es compatible con OpenAI (la misma parameters_schema
sirve para ambos providers — reconciliación §0.2).
"""

from __future__ import annotations

from app.modules.bots.services.engine.providers.openai import ProviderResult, ProviderToolCall


class ClaudeProvider:
    async def complete(self, *, system, messages, tools, params) -> ProviderResult:
        ...
```

> **Contrato común `complete(system, messages, tools, params) -> ProviderResult`**: ambos adaptadores devuelven la misma dataclass. El `EmbeddedBotEngine` no sabe de OpenAI/Anthropic — habla con `ProviderResult`. El mapeo de `BotTool.parameters_schema` (JSON Schema subset común) a la forma de cada SDK lo hace el adaptador. **Selección del adaptador**: el `EmbeddedBotEngine` instancia `OpenAIProvider`/`ClaudeProvider` según `version.provider` (un dict `{BotProvider.openai: OpenAIProvider, BotProvider.claude: ClaudeProvider}`). **Import lazy de los SDK** (`import openai`/`import anthropic` dentro de `complete`) → el boot/smoke sin las deps no rompe (el smoke mockea el adaptador).

### `engine/tools/__init__.py` — `TOOL_REGISTRY` + `@register_tool` + `BotInvocationContext`

```python
"""
Registry de tools del bot. Cada tool del catálogo (bot_tool) cuyo target_service esté
registrado acá se puede invocar; si no está → TOOL_NOT_REGISTERED (404) en runtime. La key del
registry = el `code` de la BotTool (= name que el LLM invoca). El decorator @register_tool la
inscribe al importar el módulo de tools. BotInvocationContext lleva el contexto sistémico (NO un
CurrentAuth — las tools validan reglas de negocio sistémicas, corren como SYSTEM).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BotInvocationContext:
    conversation_id: str
    person_id: str | None              # el contacto del hilo (puede ser None en bordes)
    bot_configuration_id: str
    bot_tool_call_id: str              # la traza BotToolCall en curso (para correlación)


# code -> async fn (args: dict, ctx, db) -> dict (el result que vuelve al LLM, JSON-serializable)
ToolFn = Callable[[dict[str, Any], BotInvocationContext, AsyncSession], Awaitable[dict[str, Any]]]
TOOL_REGISTRY: dict[str, ToolFn] = {}


def register_tool(code: str) -> Callable[[ToolFn], ToolFn]:
    def _wrap(fn: ToolFn) -> ToolFn:
        TOOL_REGISTRY[code] = fn
        return fn
    return _wrap
```

### `engine/tools/crm.py` / `engine/tools/catalog.py` — implementaciones MVP

```python
# engine/tools/crm.py
"""
Tools MVP que tocan crm. Corren como SYSTEM (sin CurrentAuth): las reglas las impone el service
de crm (matriz de transición, dedup de identifier, etc.). Reusan las firmas REALES verificadas:
- crm.person.find_by_identifier_or_create(db, channel_type, identifier, profile, *, campaign_id=None)
- crm.lead_activity.log(db, person_id, ActivityType, *, advisor_user_id, actor_id, content=None,
    payload=None, related_conversation_id=None, ...)
- crm.person_lead_status.transition(db, person_id, to_lead_status_id, *, actor_id, reason=None)
"""

from __future__ import annotations

from typing import Any

from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.crm.enums import ActivityType, ChannelType
from app.modules.crm.schemas.person import PersonCreate
from app.modules.crm.services import lead_activity as crm_lead_activity
from app.modules.crm.services import person as crm_person
from app.modules.crm.services import person_lead_status as crm_lead_status

SYSTEM_USER_ID = crm_person.SYSTEM_USER_ID


@register_tool("resolve_or_create_contact")
async def resolve_or_create_contact(args: dict[str, Any], ctx: BotInvocationContext, db) -> dict:
    """Resuelve/crea el contacto por (channel_type, identifier). Idempotente. Devuelve el
    person_id + full_name para que el bot continúe."""
    person = await crm_person.find_by_identifier_or_create(
        db,
        ChannelType(args.get("channel_type", ChannelType.whatsapp.value)),
        args["identifier"],
        profile=PersonCreate(
            first_name=(args.get("first_name") or "Contacto")[:80],
            last_name=(args.get("last_name") or "(WhatsApp)")[:80],
            identifiers=[],
        ),
    )
    return {"person_id": person.id, "full_name": f"{person.first_name} {person.last_name}".strip()}


@register_tool("register_lead_note")
async def register_lead_note(args: dict[str, Any], ctx: BotInvocationContext, db) -> dict:
    """Registra una NOTA en el timeline del lead, atada a la conversación (audit trail). Reusa
    lead_activity.log con related_conversation_id (el bot escribe como SYSTEM)."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    activity = await crm_lead_activity.log(
        db, ctx.person_id, ActivityType.NOTE,
        advisor_user_id=None, actor_id=SYSTEM_USER_ID,
        content=args["content"][:4000], related_conversation_id=ctx.conversation_id,
        payload={"source": "bot", "bot_configuration_id": ctx.bot_configuration_id},
    )
    return {"ok": True, "activity_id": activity.id}


@register_tool("set_lead_status")
async def set_lead_status(args: dict[str, Any], ctx: BotInvocationContext, db) -> dict:
    """Transiciona el estado del lead (valida la matriz de crm → LEAD_TRANSITION_NOT_ALLOWED).
    requires_confirmation=true en el catálogo. Devuelve ok/error (no propaga la excepción al
    loop — la captura y la reporta como result de la tool)."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    try:
        await crm_lead_status.transition(
            db, ctx.person_id, args["to_lead_status_id"],
            actor_id=SYSTEM_USER_ID, reason=args.get("reason", "Transición por bot"),
        )
        return {"ok": True}
    except Exception as exc:   # matriz / estado final → reportar al LLM, no romper el turno
        return {"ok": False, "error": str(exc)[:255]}
```

```python
# engine/tools/catalog.py
"""
Tools MVP de solo-lectura sobre catalog (info de productos/servicios). Reusan list_active:
- catalog.vertical.list_active(db)
- catalog.service.list_active(db, vertical_id=None)
- catalog.product.list_active(db, service_id=None)
"""

from __future__ import annotations

from typing import Any

from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.catalog.services import product as catalog_product
from app.modules.catalog.services import service as catalog_service
from app.modules.catalog.services import vertical as catalog_vertical


@register_tool("list_verticals")
async def list_verticals(args: dict[str, Any], ctx: BotInvocationContext, db) -> dict:
    rows = await catalog_vertical.list_active(db)
    return {"verticals": [{"id": v.id, "name": v.name} for v in rows]}


@register_tool("list_services_by_vertical")
async def list_services_by_vertical(args: dict[str, Any], ctx: BotInvocationContext, db) -> dict:
    rows = await catalog_service.list_active(db, vertical_id=args.get("vertical_id"))
    return {"services": [{"id": s.id, "name": s.name} for s in rows]}


@register_tool("list_products_by_vertical")
async def list_products_by_vertical(args: dict[str, Any], ctx: BotInvocationContext, db) -> dict:
    # MVP: list_active de catalog scopea por service_id; "por vertical" se compone
    # iterando los services del vertical o se ajusta el repo (anotado para F2).
    rows = await catalog_product.list_active(db, service_id=args.get("service_id"))
    return {"products": [{"id": p.id, "name": p.name} for p in rows]}
```

> **DIFERIDAS (NO seedear)**: `book_appointment` / `check_availability` / `cancel_appointment` → `scheduling.*` (módulo #7, no existe). Quedan documentadas en `bot_tool` solo si alguien las crea manualmente; su `target_service` apuntaría a `scheduling.*` → NO está en `TOOL_REGISTRY` → el dispatcher da `TOOL_NOT_REGISTERED` (404 runtime). Se cablean (`@register_tool`) cuando scheduling ship (reconciliación §0.4).
> **Las tools NO reciben `CurrentAuth`**: corren como **SYSTEM** (`SYSTEM_USER_ID`, seed crm F0). Las reglas de negocio (matriz de transición, dedup, etc.) las impone el service de crm. Por eso `set_lead_status` envuelve la excepción y la devuelve como `result` de la tool (el LLM la ve y puede explicarle al usuario), en vez de propagarla y romper el turno.

### `engine/embedded.py` — `EmbeddedBotEngine.dispatch_turn` (pseudocódigo del flujo §1)

```python
"""
EmbeddedBotEngine: corre un turno completo (flujo §1 de la spec). Lee el historial del hilo de
FIRESTORE (ADR-011), llama al adaptador del provider, corre el loop de tool-calling
(≤ MAX_TOOL_ITERATIONS_PER_TURN), responde con conversations.message.send_bot_outbound y
persiste las trazas (BotEvent / BotToolCall) + actualiza ConversationBotState. NO lanza 5xx
salvo para forzar el reintento de Cloud Tasks.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.core import firestore
from app.modules.bots.enums import BotEventType, BotProvider, ToolCallStatus
from app.modules.bots.services.engine.base import BotEngine, choose_bot_for_conversation
from app.modules.bots.services.engine.providers.openai import OpenAIProvider
from app.modules.bots.services.engine.providers.claude import ClaudeProvider
from app.modules.bots.services.engine.tools import TOOL_REGISTRY, BotInvocationContext
from app.modules.conversations.repositories.conversation import conversation_repository
from app.modules.conversations.services import message as conv_message
from app.shared.utils import generate_uuid, utc_now

logger = logging.getLogger(__name__)

_PROVIDER_ADAPTERS = {BotProvider.openai: OpenAIProvider, BotProvider.claude: ClaudeProvider}


class EmbeddedBotEngine(BotEngine):
    async def dispatch_turn(
        self, db: AsyncSession, *, conversation_id: str, input_message_id: str | None
    ) -> None:
        settings = get_settings()
        # 0. cargar el hilo + validar que sea un hilo de bot.
        conv = await conversation_repository.get_by_id(db, conversation_id)
        if conv is None:
            raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
        if conv.assignee_type != "bot":
            raise BadRequestException("La conversación no está asignada a un bot", code="CONVERSATION_NOT_BOT")
        config = await choose_bot_for_conversation(db, conv)
        if config is None or config.current_version_id is None:
            raise BadRequestException("El bot no tiene versión vigente", code="NO_CURRENT_VERSION")
        version = await bot_configuration_version_repository.get_by_id(db, config.current_version_id)

        # 1. ConversationBotState (load-or-create) — congela la versión con la que arranca el hilo.
        state = await conversation_bot_state_repository.get_by_conversation(db, conversation_id)
        if state is None:
            state = ConversationBotState(
                id=generate_uuid(), conversation_id=conversation_id,
                bot_configuration_id=config.id, bot_configuration_version_id=version.id,
                collected_slots={}, turn_count=0, active=True,
                created_by=SYSTEM_USER_ID, created_on=utc_now(),
                updated_by=SYSTEM_USER_ID, updated_on=utc_now(),
            )
            db.add(state); await db.flush()

        # Guard de costo: max_turns_per_conversation (None = sin límite).
        if config.max_turns_per_conversation is not None and state.turn_count >= config.max_turns_per_conversation:
            logger.info("bot turn cap reached", extra={"conversation_id": conversation_id})
            return   # silencioso (el handoff automático a humano = F4)

        # 2. BotEvent(turn_started).
        turn_number = await bot_event_repository.max_turn_number(db, conversation_id) + 1
        started = utc_now()
        event = BotEvent(
            id=generate_uuid(), conversation_id=conversation_id,
            bot_configuration_id=config.id, bot_configuration_version_id=version.id,
            turn_number=turn_number, event_type=BotEventType.turn_started.value,
            input_message_id=input_message_id, active=True,
            created_by=SYSTEM_USER_ID, created_on=started, updated_by=SYSTEM_USER_ID, updated_on=started,
        )
        db.add(event); await db.flush()

        # 3. prompt = system_prompt + historial Firestore + tools (M:N ∩ active).
        history = firestore.list_message_docs(conversation_id, skip=0, limit=50)[0]  # del hilo (ADR-011)
        messages = _map_history_to_messages(history)   # docs Firestore → [{role, content}]
        tools_models = await bot_tool_repository.active_tools_for_config(db, config.id)
        tools_defs = [_tool_to_schema(t) for t in tools_models]   # parameters_schema → forma común
        tool_by_code = {t.code: t for t in tools_models}

        # 4. engine_factory ya eligió EmbeddedBotEngine; acá se elige el ADAPTADOR del provider.
        adapter = _PROVIDER_ADAPTERS[BotProvider(version.provider)]()

        # 5. loop de tool-calling (≤ MAX_TOOL_ITERATIONS_PER_TURN).
        tokens_in = tokens_out = 0
        output_text: str | None = None
        for _ in range(settings.MAX_TOOL_ITERATIONS_PER_TURN):
            result = await adapter.complete(
                system=version.system_prompt, messages=messages,
                tools=tools_defs, params=version.parameters,
            )
            tokens_in += result.tokens_in or 0
            tokens_out += result.tokens_out or 0
            if not result.tool_calls:
                output_text = result.text
                break   # el modelo respondió al usuario → fin del loop
            # ejecutar cada tool pedida → BotToolCall(pending→success/error) → re-prompt.
            for call in result.tool_calls:
                tool_model = tool_by_code.get(call.name)
                fn = TOOL_REGISTRY.get(tool_model.target_service if tool_model else call.name)
                tc = BotToolCall(
                    id=generate_uuid(), conversation_id=conversation_id, bot_event_id=event.id,
                    bot_tool_id=(tool_model.id if tool_model else None),
                    tool_use_id=call.tool_use_id, arguments=call.arguments,
                    status=ToolCallStatus.pending.value, started_at=utc_now(), active=True,
                    created_by=SYSTEM_USER_ID, created_on=utc_now(), updated_by=SYSTEM_USER_ID, updated_on=utc_now(),
                )
                db.add(tc); await db.flush()
                if fn is None:        # tool del catálogo sin implementación registrada
                    tc.status = ToolCallStatus.error.value
                    tc.error_message = "TOOL_NOT_REGISTERED"
                    tool_result = {"ok": False, "error": "tool_not_registered"}
                else:
                    ctx = BotInvocationContext(
                        conversation_id=conversation_id, person_id=conv.person_id,
                        bot_configuration_id=config.id, bot_tool_call_id=tc.id,
                    )
                    t0 = utc_now()
                    try:
                        tool_result = await fn(call.arguments, ctx, db)
                        tc.status = ToolCallStatus.success.value
                    except Exception as exc:   # noqa: BLE001 — reportar al LLM, no romper el turno
                        tc.status = ToolCallStatus.error.value
                        tc.error_message = str(exc)[:1000]
                        tool_result = {"ok": False, "error": str(exc)[:255]}
                    tc.latency_ms = int((utc_now() - t0).total_seconds() * 1000)
                tc.result = tool_result
                tc.completed_at = utc_now()
                messages.append(_tool_result_message(call, tool_result))   # re-prompt con el result
            await db.flush()
        else:
            # agotó las iteraciones sin una respuesta final → fallback configurable.
            output_text = _fallback_text(version)

        # 6. responder por WhatsApp reusando conversations (sender_type='bot').
        output_mid: str | None = None
        if output_text:
            sent = await conv_message.send_bot_outbound(
                db, conv, output_text, bot_configuration_id=config.id)
            output_mid = sent.mid

        # 7. update ConversationBotState + BotEvent(turn_completed).
        state.turn_count += 1
        state.last_bot_turn_at = utc_now()
        state.updated_by = SYSTEM_USER_ID; state.updated_on = utc_now()
        db.add(BotEvent(
            id=generate_uuid(), conversation_id=conversation_id,
            bot_configuration_id=config.id, bot_configuration_version_id=version.id,
            turn_number=turn_number, event_type=BotEventType.turn_completed.value,
            input_message_id=input_message_id, output_message_id=output_mid,
            tokens_in=tokens_in, tokens_out=tokens_out,
            latency_ms=int((utc_now() - started).total_seconds() * 1000),
            cost_estimated_usd=_estimate_cost(version, tokens_in, tokens_out),
            event_metadata={"provider": version.provider, "model": version.model_name},
            active=True, created_by=SYSTEM_USER_ID, created_on=utc_now(),
            updated_by=SYSTEM_USER_ID, updated_on=utc_now(),
        ))
        await db.flush()


async def dispatch_turn(db, *, conversation_id: str, input_message_id: str | None) -> None:
    """Entrypoint que usan el router /engine/dispatch y dispatch-manual. Carga el bot del hilo,
    elige el engine (engine_factory por el provider de la versión vigente) y corre el turno. Las
    fallas de provider se capturan como BotEvent(turn_failed) + mensaje de fallback; el turno NO
    devuelve 5xx a Cloud Tasks salvo que queramos forzar el reintento."""
    try:
        # engine_factory necesita la versión vigente → resolver bot + versión primero.
        conv = await conversation_repository.get_by_id(db, conversation_id)
        if conv is None:
            raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
        config = await choose_bot_for_conversation(db, conv)
        if config is None or config.current_version_id is None:
            raise BadRequestException("El bot no tiene versión vigente", code="NO_CURRENT_VERSION")
        version = await bot_configuration_version_repository.get_by_id(db, config.current_version_id)
        engine = engine_factory(version)   # EmbeddedBotEngine | PROVIDER_NOT_SUPPORTED
        await engine.dispatch_turn(db, conversation_id=conversation_id, input_message_id=input_message_id)
    except BadRequestException:
        raise   # CONVERSATION_NOT_BOT / NO_CURRENT_VERSION / PROVIDER_NOT_SUPPORTED → 400 (debugging visible)
    except Exception as exc:   # provider error / red → log + BotEvent(turn_failed) + fallback
        logger.warning("bot turn failed", extra={"conversation_id": conversation_id, "error": str(exc)})
        await _log_turn_failed(db, conversation_id, error=str(exc))
        # NO re-raise (no forzar reintento de Cloud Tasks por un error de provider — evitaría
        # spamear al usuario con reintentos). El fallback ya se envió en _log_turn_failed.
```

> **Flujo del turno (mapeo §1 de la spec)**: (1) load-or-create `ConversationBotState` + resolver versión vigente; (2) `BotEvent(turn_started, turn_number, input_message_id=mid)`; (3) prompt = `system_prompt` + historial **Firestore** (`firestore.list_message_docs`) + tools (M:N ∩ `active`); (4) `engine_factory(version)` → `EmbeddedBotEngine` → adaptador del provider; (5) loop de tool-calling ≤ `MAX_TOOL_ITERATIONS_PER_TURN` (`BotToolCall(pending)` → `TOOL_REGISTRY[code](args, ctx, db)` → `BotToolCall(success/error)` → re-prompt); (6) `conversations.message.send_bot_outbound(...)` → `output_mid`; (7) update `ConversationBotState` (slots/intent/turn_count/last_bot_turn_at) + `BotEvent(turn_completed, tokens/cost/latency)`. Errores → `BotEvent(turn_failed)` + mensaje de fallback configurable.
> **`MAX_TOOL_ITERATIONS_PER_TURN`** (Settings, default 5): corta loops infinitos de tool-calling (el modelo pidiendo tools sin converger a una respuesta). Al agotarse → fallback configurable (el `else` del `for`).
> **`TOOL_REGISTRY` se indexa por `target_service`** (la columna de `BotTool`) en el dispatcher — el `code` que el LLM invoca se mapea a la `BotTool` por `code`, y de ahí al `target_service` que es la key del registry. Si la `BotTool` existe pero su `target_service` no está registrado → `BotToolCall(error, "TOOL_NOT_REGISTERED")` y se le reporta al LLM (sin romper el turno). **Decisión**: el registry se indexa por `code` en `@register_tool("resolve_or_create_contact")` (= el `code`/`name` de la tool), y `target_service` se usa como referencia documental del catálogo; el dispatcher resuelve `TOOL_REGISTRY[tool.code]`. Ver `deviations` (la spec dice "target_service resuelto por TOOL_REGISTRY"; en la práctica el `code` y el `target_service` son 1:1 para las tools MVP).
> **El turno corre en UNA `AsyncSession`** (la del request `/engine/dispatch`, commiteada por `get_db` al final). El `send_bot_outbound` encola el outbox + escribe Firestore (igual que el `send_outbound` del asesor); el relay síncrono lo dispara el router de dispatch (mismo patrón que el webhook/composer de conversations — evita el ciclo de import).

---

## 7. `app/core/cloud_tasks.py` — cliente lazy + `enqueue_turn` (ADR-012)

Cross-cutting reusable (molde `app/core/secrets.py`/`firestore.py`): cliente del SDK de Cloud Tasks **lazy** (no al import → el boot/smoke sin GCP no rompe) + helper `enqueue_turn` que crea una tarea HTTP con token **OIDC** apuntando a `POST /api/v1/bots/engine/dispatch`.

```python
"""
Cloud Tasks dispatch del turno del bot (ADR-012). El webhook de conversations, tras su pipe
síncrono, encola UNA tarea (enqueue_turn) → la cola la entrega a POST /api/v1/bots/engine/dispatch
con un token OIDC (Cloud Run valida el audience). El endpoint corre dispatch_turn con CPU
asignada (el turno llama a un LLM = segundos + loops de tool-calling). Reintentos+backoff+DLQ+
rate-limit los configura la COLA (infra/CI), no el código.

- El cliente del SDK se inicializa LAZY (no al import) → la app bootea sin GCP (local/test).
- En local/dev (ENV_NAME=dev o CLOUD_TASKS_QUEUE vacío) enqueue_turn es NO-OP (o llama el
  dispatch inline para debugging — flag CLOUD_TASKS_INLINE). El smoke NUNCA toca Cloud Tasks.
- La SA de Cloud Run necesita roles/cloudtasks.enqueuer + actuar como la SA del OIDC token
  (roles/iam.serviceAccountUser sobre la SA invoker).
Dep nueva: google-cloud-tasks>=2.16,<3 (pin en pyproject.toml).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None  # lazy CloudTasksAsyncClient


def _get_client() -> Any:
    global _client
    if _client is None:
        from google.cloud import tasks_v2   # import diferido (solo Cloud Run)
        _client = tasks_v2.CloudTasksAsyncClient()
    return _client


async def enqueue_turn(*, conversation_id: str, input_message_id: str | None) -> None:
    """Encola un turno del bot. NO-OP en dev / sin cola configurada (el webhook ya respondió
    200 a Meta; en local el dispatch se prueba vía /engine/dispatch-manual). El payload va al
    endpoint interno con un token OIDC (audience = la URL del servicio)."""
    settings = get_settings()
    if not settings.CLOUD_TASKS_QUEUE or settings.ENV_NAME == "dev":
        logger.info("cloud tasks disabled; skipping bot turn enqueue",
                    extra={"conversation_id": conversation_id})
        return
    parent = _get_client().queue_path(
        settings.GCP_PROJECT_ID, settings.CLOUD_TASKS_LOCATION, settings.CLOUD_TASKS_QUEUE)
    url = f"{settings.SERVICE_BASE_URL}{settings.API_V1_PREFIX}/bots/engine/dispatch"
    body = json.dumps(
        {"conversation_id": conversation_id, "input_message_id": input_message_id}
    ).encode()
    task = {
        "http_request": {
            "http_method": "POST",
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": settings.CLOUD_TASKS_INVOKER_SA,
                "audience": settings.SERVICE_BASE_URL,
            },
        }
    }
    await _get_client().create_task(parent=parent, task=task)
```

> **Settings nuevos** (en `app/core/config.py:Settings`, defaults vacíos para que el smoke `ENV_NAME=dev` no toque nada): `OPENAI_API_KEY: str = ""`, `ANTHROPIC_API_KEY: str = ""`, `BOT_DEFAULT_MODEL: str = "gpt-4.1-mini"`, `MAX_TOOL_ITERATIONS_PER_TURN: int = 5`, `CLOUD_TASKS_QUEUE: str = ""`, `CLOUD_TASKS_LOCATION: str = "us-central1"`, `CLOUD_TASKS_INVOKER_SA: str = ""`, `SERVICE_BASE_URL: str = ""` (la URL pública del servicio Cloud Run, para construir el target del task + el audience OIDC). `GCP_PROJECT_ID` ya existe (lo agregó conversations). **Deps runtime**: `openai>=1.x` (nueva), `anthropic>=0.40` (ya está por conversations), `google-cloud-tasks>=2.16,<3` (nueva). **Agregar `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` a `--set-secrets` y `CLOUD_TASKS_*`/`SERVICE_BASE_URL`/`BOT_DEFAULT_MODEL`/`MAX_TOOL_ITERATIONS_PER_TURN` a `--set-env-vars` de AMBOS workflows deploy** (lección transversal §0.7/§0.15 de conversations: los workflows backend NO seteaban env vars nuevas).

---

## 8. Enganches a `conversations` (cambios aditivos)

> Todos backward-compatible. Sin bot configurado en el canal → comportamiento de conversations intacto.

### 8.1 `message.send_bot_outbound` (CAMBIO #1) — outbound del bot

`conversations.message.send_outbound` exige `assignee_type=='advisor'` + `actor==assignee` → un bot daría `NOT_CONVERSATION_ASSIGNEE`. Se agrega una función **hermana** (sin tocar `send_outbound`), que valida `assignee_type=='bot'` y reusa el MISMO pipe (Meta Graph API + outbox + relay):

```python
# conversations/services/message.py — aditivo
async def send_bot_outbound(
    db, conversation: Conversation, content: str, *, bot_configuration_id: str
) -> SingleResponse[MessageItem]:
    """Outbound de un BOT (no de un asesor). Valida assignee_type=='bot' (sino
    CONVERSATION_NOT_BOT / NOT_CONVERSATION_ASSIGNEE), persiste con sender_type='bot',
    sender_user_id=None, bot_configuration_id en el doc. Reusa el mismo Meta send + outbox +
    relay que send_outbound. Devuelve el `mid` outbound (→ BotEvent.output_message_id)."""
    if conversation.status != ConversationStatus.open.value:
        raise BadRequestException("La conversación está cerrada", code="CONVERSATION_NOT_OPEN")
    if conversation.assignee_type != AssigneeType.bot.value:
        raise BadRequestException("La conversación no está asignada a un bot", code="CONVERSATION_NOT_BOT")
    mid = generate_uuid()
    doc = {
        "id": mid, "conversation_id": conversation.id,
        "direction": MessageDirection.outbound.value, "sender_type": SenderType.bot.value,
        "sender_user_id": None, "bot_configuration_id": bot_configuration_id,
        "content_type": ContentType.text.value, "content": content,
        "external_id": None, "external_status": MessageExternalStatus.sent.value,
        "sent_at": _iso(utc_now()), "delivered_at": None, "read_at": None,
        "failed_at": None, "failure_reason": None, "attachments": [], "created_at": _iso(utc_now()),
    }
    # envío real a Meta (igual que send_outbound) → external_id/failed; persiste en outbox +
    # denorm del conversation; el relay (router de dispatch) proyecta a Firestore. SIEMPRE persiste.
    ...
    return SingleResponse(data=_doc_to_message_item(doc))   # .data.id == el mid (output_message_id)
```

> **Sin advisor-assignee check** (a diferencia de `send_outbound`): el bot NO es un usuario; valida solo que el hilo esté `assignee_type=='bot'`. `sender_type='bot'`, `sender_user_id=None`, `bot_configuration_id` en el doc (lo lee la UI para badge "Bot" + lo usa la analítica). El engine consume el `mid` devuelto como `BotEvent.output_message_id`.

### 8.2 Hook en `find_or_create_open` (CAMBIO #2) — asignación al bot

Hoy `find_or_create_open` asigna a advisor (dueño del lead) o `unassigned`, **nunca a bot**. Se agrega el hook: si `channel_account.bot_configuration_id` está set, las conversaciones NUEVAS de ese canal arrancan `assignee_type='bot'` con ese bot, **antes** de la auto-asignación al asesor:

```python
# conversations/services/conversation.py — find_or_create_open, tras el get_open / antes de advisor_map
if channel_account.bot_configuration_id is not None:
    assignee_type, assignee_user_id = AssigneeType.bot, None
    bot_configuration_id = channel_account.bot_configuration_id
else:
    advisor_map = await lead_assignment_repository.advisor_map(db, [person_id])
    advisor_id = advisor_map.get(person_id)
    assignee_type, assignee_user_id = (
        (AssigneeType.advisor, advisor_id) if advisor_id else (AssigneeType.unassigned, None)
    )
    bot_configuration_id = None
# ... el Conversation se crea con assignee_type/assignee_user_id/bot_configuration_id de arriba.
```

> **El handoff del asesor (F3 `take`) cambia a `assignee_type='advisor'`** → el bot deja de responder (el webhook solo encola la task si `assignee_type=='bot'`). `release` a `bot` reactiva el bot (`conversations` ya tiene la rama `to_assignee_type==bot` con `to_bot_configuration_id`, hoy guardada como inválida porque bots no existía; con bots se habilita pasando el `bot_configuration_id`). Sin bot en el canal → la rama vieja (advisor/unassigned) intacta.

### 8.3 Enqueue en el webhook processor (CAMBIO #3) — disparar el turno

Tras el pipe síncrono del webhook (persist_inbound + enqueue del relay), si el hilo quedó `assignee_type=='bot'`, encolar la Cloud Task:

```python
# conversations/services/webhook_processor/whatsapp.py — process_inbound, tras persist_inbound
if conv.assignee_type == AssigneeType.bot.value:
    from app.core import cloud_tasks
    await cloud_tasks.enqueue_turn(conversation_id=conv.id, input_message_id=m["id"])
```

> **Por qué Cloud Tasks y no BackgroundTasks** (ADR-012): el turno del bot llama a un LLM (segundos + loops de tool-calling) = trabajo lento must-complete. `BackgroundTasks` corre en el mismo proceso/instancia (riesgo de cancelación al apagar la instancia, sin reintento, CPU throttled tras el response en Cloud Run). Cloud Tasks da un request fresco con CPU asignada + reintentos/backoff/DLQ. El webhook responde 200 a Meta inmediato; el turno corre desacoplado. **El enqueue es NO-OP en dev** (`cloud_tasks.enqueue_turn` lo cortocircuita) → el smoke valida el pipe síncrono + el `assignee_type='bot'`, no Cloud Tasks. El dispatch se prueba en QA/manual vía `/engine/dispatch-manual`.

---

## 9. Routers + permisos exactos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; `actor: CurrentAuth` aparte cuando se necesita el id para audit; `/active` antes de `/{id}`.

### 9.1 Configuraciones + versiones + tools M:N — `/api/v1/bots/`

| Método | Ruta | Permiso | Envelope / Body |
|---|---|---|---|
| POST | `/configurations/list` | `BOT_CONFIGURATIONS_READ` | `QueryRequest` → `PaginatedResponse[BotConfigurationItem]` |
| POST | `/configurations` | `BOT_CONFIGURATIONS_CREATE` | `BotConfigurationCreate` → `201 SingleResponse[BotConfigurationDetail]` |
| GET | `/configurations/active` | `BOT_CONFIGURATIONS_READ` | lista cruda `list[BotConfigurationOption]` |
| GET | `/configurations/{id}` | `BOT_CONFIGURATIONS_READ` | `SingleResponse[BotConfigurationDetail]` |
| PUT | `/configurations/{id}` | `BOT_CONFIGURATIONS_UPDATE` | `BotConfigurationUpdate` → `SingleResponse[BotConfigurationDetail]` |
| DELETE | `/configurations/{id}` | `BOT_CONFIGURATIONS_DELETE` | `204` (soft-delete) |
| GET | `/configurations/{id}/versions` | `BOT_CONFIGURATION_VERSIONS_READ` | `SingleResponse[list[BotConfigurationVersionItem]]` |
| POST | `/configurations/{id}/versions` | `BOT_CONFIGURATION_VERSIONS_WRITE` | `BotConfigurationVersionCreate` → `201 SingleResponse[BotConfigurationVersionDetail]` |
| GET | `/configurations/{id}/versions/{vid}` | `BOT_CONFIGURATION_VERSIONS_READ` | `SingleResponse[BotConfigurationVersionDetail]` |
| POST | `/configurations/{id}/activate-version/{vid}` | `BOT_CONFIGURATION_VERSIONS_WRITE` | `SingleResponse[BotConfigurationDetail]` |
| GET | `/configurations/{id}/tools` | `BOT_CONFIGURATIONS_READ` | `SingleResponse[list[BotToolOption]]` (tools del bot) |
| PUT | `/configurations/{id}/tools` | `BOT_CONFIGURATIONS_UPDATE` | `ConfigurationToolsUpdate` (`{tool_ids:[]}`) → `SingleResponse[BotConfigurationDetail]` |

### 9.2 Catálogo de tools — `/api/v1/bots/tools/`

| Método | Ruta | Permiso | Envelope / Body |
|---|---|---|---|
| POST | `/tools/list` | `BOT_TOOLS_READ` | `QueryRequest` → `PaginatedResponse[BotToolItem]` |
| GET | `/tools/active` | `BOT_TOOLS_READ` | lista cruda `list[BotToolOption]` |
| POST | `/tools` | `BOT_TOOLS_WRITE` | `BotToolCreate` → `201 SingleResponse[BotToolDetail]` |
| PUT | `/tools/{id}` | `BOT_TOOLS_WRITE` | `BotToolUpdate` → `SingleResponse[BotToolDetail]` |
| DELETE | `/tools/{id}` | `BOT_TOOLS_WRITE` | `204` (soft-delete) |

### 9.3 Estado / trazas (depuración) — `/api/v1/bots/conversations/{cid}/`

| Método | Ruta | Permiso | Envelope / Body |
|---|---|---|---|
| GET | `/conversations/{cid}/state` | `BOT_STATE_READ` | `SingleResponse[ConversationBotStateDetail]` |
| POST | `/conversations/{cid}/state/reset` | `BOT_STATE_WRITE` | `ResetBotStateRequest` → `SingleResponse[ConversationBotStateDetail]` |
| GET | `/conversations/{cid}/events` | `BOT_EVENTS_READ` | `SingleResponse[list[BotEventItem]]` (timeline de turnos) |
| GET | `/conversations/{cid}/tool-calls` | `BOT_TOOL_CALLS_READ` | `SingleResponse[list[BotToolCallItem]]` |

### 9.4 Engine — `/api/v1/bots/engine/`

| Método | Ruta | Auth | Envelope / Body |
|---|---|---|---|
| POST | `/engine/dispatch` | **OIDC / shared-secret, NO RBAC** (target de Cloud Tasks) | `DispatchTurnRequest` → `200 {success:true}` |
| POST | `/engine/dispatch-manual` | `BOT_ENGINE_INVOKE` (debugging de admin) | `DispatchTurnRequest` → `SingleResponse[ConversationBotStateDetail]` |

```python
# routers/engine.py (extracto)
from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import CurrentAuth, DBSession
from app.core.permissions import RequirePermission
from app.modules.bots.schemas.engine import DispatchTurnRequest
from app.modules.bots.services.engine import embedded as engine
from app.modules.conversations.services import message as conv_message

router = APIRouter(prefix="/engine", tags=["bots"])


async def verify_oidc(request: Request) -> None:
    """Auth del dispatch interno: valida el token OIDC que Cloud Tasks adjunta (audience =
    SERVICE_BASE_URL). En Cloud Run, el ingress/IAM ya valida el OIDC del invoker SA; acá se
    re-chequea el audience/issuer del Authorization: Bearer. En dev (sin GCP) se acepta un
    shared-secret header (X-Bot-Dispatch-Secret == Settings.BOT_DISPATCH_SECRET)."""
    ...


@router.post("/dispatch", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_oidc)])
async def dispatch(payload: DispatchTurnRequest, db: DBSession) -> dict:
    """Target de Cloud Tasks. SIN RBAC (lo invoca la cola con OIDC). Corre el turno; dispara el
    relay síncrono del outbox a Firestore tras el flush (mismo patrón que el webhook/composer)."""
    await engine.dispatch_turn(
        db, conversation_id=payload.conversation_id, input_message_id=payload.input_message_id)
    await conv_message.relay_outbox(db)   # proyecta el outbound del bot a Firestore (síncrono)
    return {"success": True}


@router.post("/dispatch-manual", dependencies=[Depends(RequirePermission("BOT_ENGINE_INVOKE"))])
async def dispatch_manual(
    payload: DispatchTurnRequest, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ConversationBotStateDetail]:
    """Dispatch MANUAL para debugging (admin con BOT_ENGINE_INVOKE). Corre el turno inline y
    devuelve el estado resultante del bot. Útil en QA sin Cloud Tasks."""
    await engine.dispatch_turn(
        db, conversation_id=payload.conversation_id, input_message_id=payload.input_message_id)
    await conv_message.relay_outbox(db)
    return await state_service.get_state(db, payload.conversation_id)
```

> **`/engine/dispatch` SIN RBAC**: lo invoca Cloud Tasks con un token **OIDC** (Cloud Run valida el audience del invoker SA). NO usa `RequirePermission`/`CurrentAuth`. La defensa de fondo es el IAM de Cloud Run (`--no-allow-unauthenticated` + el invoker SA con `roles/run.invoker`); `verify_oidc` re-chequea el audience. En dev (sin GCP) acepta un `X-Bot-Dispatch-Secret` (`Settings.BOT_DISPATCH_SECRET`). **`BOT_ENGINE_INVOKE` gatea SOLO el dispatch MANUAL** (admin, debugging). **El relay síncrono** del outbox lo dispara el router (igual que el composer/webhook de conversations — evita el ciclo de import con `conversation`).

---

## 10. Permisos y roles (14 perms — F0 los agrega a seed)

Canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md) (`module="BOTS"`). **NO redefinir** — solo agregarlos a `SEED_PERMISSIONS` (formato `{"code", "name", "module"}`):

`MENU-BOTS` · `BOT_CONFIGURATIONS_READ` · `BOT_CONFIGURATIONS_CREATE` · `BOT_CONFIGURATIONS_UPDATE` · `BOT_CONFIGURATIONS_DELETE` · `BOT_CONFIGURATION_VERSIONS_READ` · `BOT_CONFIGURATION_VERSIONS_WRITE` · `BOT_TOOLS_READ` · `BOT_TOOLS_WRITE` · `BOT_STATE_READ` · `BOT_STATE_WRITE` · `BOT_EVENTS_READ` · `BOT_TOOL_CALLS_READ` · `BOT_ENGINE_INVOKE`.

- **ADMIN**: todos.
- **ASESOR**: read-only — `MENU-BOTS`, `BOT_CONFIGURATIONS_READ`, `BOT_STATE_READ`, `BOT_EVENTS_READ`, `BOT_TOOL_CALLS_READ` (puede ver qué hizo el bot en una conversación; NO configura ni dispara). **NO** `BOT_*_WRITE`/`BOT_ENGINE_INVOKE`/`BOT_CONFIGURATIONS_{CREATE,UPDATE,DELETE}`.
- **DOCTOR**: sin permisos en bots.

> El `/engine/dispatch` NO usa RBAC (OIDC de Cloud Tasks). `BOT_ENGINE_INVOKE` gatea solo `/engine/dispatch-manual`. Los sets `ASESOR_PERMISSION_CODES`/`ADMIN_PERMISSION_CODES` se filtran por código (idempotente, a prueba de orden de módulos). El user/role `SYSTEM` (`00000000-0000-0000-0000-000000000002`, seed crm F0) es el `created_by`/`actor_id` de las trazas (`BotEvent`/`BotToolCall`/`ConversationBotState`) y de las tools (que corren como SYSTEM).

---

## 11. Plan de migraciones 0017 / 0018 / 0019 (revid ≤ 32 chars; down_revision encadenado)

Migraciones **manuales y numeradas**. La última aplicada es `0016_conv_threads`; `bots` encadena desde ahí. UNIQUE parciales con `WHERE deleted_at IS NULL` (Postgres) — el smoke no las corre (usa `create_all` sobre los modelos, donde el `sqlite_where` reproduce el índice). JSONB en las columnas `jsonb`. El smoke `create_all` NO corre la migración (JSONB / ALTER ADD CONSTRAINT son Postgres-only) → se valida vía QA E2E sobre Postgres (patrón crm `0013` / conversations `0016`). **El estado del bot SÍ es Postgres** (`conversation_bot_state`); el historial de mensajes que el bot lee es Firestore (sin migración Alembic).

**Cadena de revids** (todos ≤32): `0016_conv_threads` (17) → `0017_bots_configuration` (22) → `0018_bots_tools` (15) → `0019_bots_engine_state` (22). ✔

### `0017_bots_configuration.py` (F1 — bot_configuration + bot_configuration_version + forward FK constraints) · revid `0017_bots_configuration`

```python
revision = "0017_bots_configuration"
down_revision = "0016_conv_threads"
from sqlalchemy.dialects import postgresql  # JSONB

def upgrade() -> None:
    # ── bot_configuration_version (se crea ANTES para que bot_configuration.current_version_id la pueda referenciar) ──
    op.create_table(
        "bot_configuration_version",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=False),  # FK se agrega abajo (circular)
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("external_webhook_url", sa.String(length=500), nullable=True),
        sa.Column("external_webhook_secret_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    # ── bot_configuration ──
    op.create_table(
        "bot_configuration",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("bot_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("max_turns_per_conversation", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_bot_configuration_code", "bot_configuration", ["code"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("uq_bot_config_version_number", "bot_configuration_version",
        ["bot_configuration_id", "version"], unique=True)
    op.create_index("ix_bot_config_version_config_id", "bot_configuration_version", ["bot_configuration_id"])
    op.create_index("ix_bot_configuration_current_version_id", "bot_configuration", ["current_version_id"])
    # ── FKs circulares (se agregan tras existir ambas tablas) ──
    op.create_foreign_key("fk_bot_config_version_config", "bot_configuration_version",
        "bot_configuration", ["bot_configuration_id"], ["id"])
    op.create_foreign_key("fk_bot_configuration_current_version", "bot_configuration",
        "bot_configuration_version", ["current_version_id"], ["id"])
    # ── forward FK constraints ADITIVAS a conversations (ADR-009; Postgres-only) ──
    op.create_foreign_key("fk_channel_account_bot_configuration", "channel_account",
        "bot_configuration", ["bot_configuration_id"], ["id"])
    op.create_foreign_key("fk_conversation_bot_configuration", "conversation",
        "bot_configuration", ["bot_configuration_id"], ["id"])

def downgrade() -> None:
    op.drop_constraint("fk_conversation_bot_configuration", "conversation", type_="foreignkey")
    op.drop_constraint("fk_channel_account_bot_configuration", "channel_account", type_="foreignkey")
    op.drop_constraint("fk_bot_configuration_current_version", "bot_configuration", type_="foreignkey")
    op.drop_constraint("fk_bot_config_version_config", "bot_configuration_version", type_="foreignkey")
    op.drop_index("ix_bot_configuration_current_version_id", table_name="bot_configuration")
    op.drop_index("ix_bot_config_version_config_id", table_name="bot_configuration_version")
    op.drop_index("uq_bot_config_version_number", table_name="bot_configuration_version")
    op.drop_index("uq_bot_configuration_code", table_name="bot_configuration")
    op.drop_table("bot_configuration")
    op.drop_table("bot_configuration_version")
```

> **🔑 Las dos `ALTER TABLE ADD CONSTRAINT` forward** (`fk_channel_account_bot_configuration`, `fk_conversation_bot_configuration`) son las que cierran las FKs forward que `conversations` dejó como `varchar(36)` sin constraint (ADR-009). Seguras: todos los valores actuales de `channel_account.bot_configuration_id`/`conversation.bot_configuration_id` son NULL (bots no existía). **Postgres-only** (no corren en sqlite/create_all — el smoke ve esas columnas como `String(36)` plano). **NO** se agrega `relationship` ORM en conversations (mantiene su mapper intacto — patrón "sin relationship cross-módulo"). **FKs circulares `bot_configuration ↔ bot_configuration_version`**: se crean ambas tablas sin la FK inline y se agregan con `create_foreign_key` al final (Postgres resuelve la dependencia circular; en sqlite/create_all el `ForeignKey` inline del modelo es tolerado porque ambas tablas se crean juntas).

### `0018_bots_tools.py` (F2 — bot_tool + M:N bot_configuration_tool) · revid `0018_bots_tools`

```python
revision = "0018_bots_tools"
down_revision = "0017_bots_configuration"
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    op.create_table(
        "bot_tool",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parameters_schema", postgresql.JSONB(), nullable=False),
        sa.Column("target_service", sa.String(length=120), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_bot_tool_code", "bot_tool", ["code"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_table(
        "bot_configuration_tool",
        sa.Column("bot_configuration_id", sa.String(length=36),
            sa.ForeignKey("bot_configuration.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bot_tool_id", sa.String(length=36),
            sa.ForeignKey("bot_tool.id", ondelete="CASCADE"), primary_key=True),
    )

def downgrade() -> None:
    op.drop_table("bot_configuration_tool")
    op.drop_index("uq_bot_tool_code", table_name="bot_tool")
    op.drop_table("bot_tool")
```

### `0019_bots_engine_state.py` (F3 — conversation_bot_state + bot_event + bot_tool_call) · revid `0019_bots_engine_state`

```python
revision = "0019_bots_engine_state"
down_revision = "0018_bots_tools"
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # ── conversation_bot_state (PK·A·SD·T; UNIQUE conversation_id) ──
    op.create_table(
        "conversation_bot_state",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("bot_configuration_id", sa.String(length=36), sa.ForeignKey("bot_configuration.id"), nullable=False),
        sa.Column("bot_configuration_version_id", sa.String(length=36),
            sa.ForeignKey("bot_configuration_version.id"), nullable=False),
        sa.Column("current_intent", sa.String(length=80), nullable=True),
        sa.Column("collected_slots", postgresql.JSONB(), nullable=False),
        sa.Column("last_node", sa.String(length=120), nullable=True),
        sa.Column("last_bot_turn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_conversation_bot_state_conversation", "conversation_bot_state",
        ["conversation_id"], unique=True)
    # ── bot_event (PK·A·T, SIN deleted_at — traza) ──
    op.create_table(
        "bot_event",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("bot_configuration_id", sa.String(length=36), sa.ForeignKey("bot_configuration.id"), nullable=False),
        sa.Column("bot_configuration_version_id", sa.String(length=36),
            sa.ForeignKey("bot_configuration_version.id"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("input_message_id", sa.String(length=255), nullable=True),   # mid Firestore, NO FK
        sa.Column("output_message_id", sa.String(length=255), nullable=True),  # mid Firestore, NO FK
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_estimated_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_bot_event_conversation_turn", "bot_event",
        ["conversation_id", "turn_number"], unique=True)
    op.create_index("ix_bot_event_config_created", "bot_event", ["bot_configuration_id", "created_on"])
    op.create_index("ix_bot_event_type_created", "bot_event", ["event_type", "created_on"])
    # ── bot_tool_call (PK·A·T, SIN deleted_at — traza) ──
    op.create_table(
        "bot_tool_call",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("bot_event_id", sa.String(length=36), sa.ForeignKey("bot_event.id"), nullable=True),
        sa.Column("bot_tool_id", sa.String(length=36), sa.ForeignKey("bot_tool.id"), nullable=False),
        sa.Column("tool_use_id", sa.String(length=255), nullable=True),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_bot_tool_call_conversation_id", "bot_tool_call", ["conversation_id"])
    op.create_index("ix_bot_tool_call_event_id", "bot_tool_call", ["bot_event_id"])

def downgrade() -> None:
    op.drop_table("bot_tool_call")
    op.drop_index("ix_bot_event_type_created", table_name="bot_event")
    op.drop_index("ix_bot_event_config_created", table_name="bot_event")
    op.drop_index("uq_bot_event_conversation_turn", table_name="bot_event")
    op.drop_table("bot_event")
    op.drop_index("uq_conversation_bot_state_conversation", table_name="conversation_bot_state")
    op.drop_table("conversation_bot_state")
```

> **Nota dialect-agnóstica**: los **modelos** declaran el índice parcial con `postgresql_where + sqlite_where`; la **migración** escribe solo `postgresql_where`. F0 (solo seed/skeleton) y F3 más allá de la tabla no llevan migración extra (las forward FK van en 0017). El **input/output_message_id NO son FK** en la migración (varchar plano = mid Firestore).

---

## 12. Seed (14 perms + un bot semilla)

### Permisos (F0 — `app/core/seed.py:SEED_PERMISSIONS`)

```python
# ── Module: bots (14 permisos) ──────────────────────────────────────
{"code": "MENU-BOTS", "name": "Menu Bots", "module": "BOTS"},
{"code": "BOT_CONFIGURATIONS_READ", "name": "Read bot configurations", "module": "BOTS"},
{"code": "BOT_CONFIGURATIONS_CREATE", "name": "Create bot configurations", "module": "BOTS"},
{"code": "BOT_CONFIGURATIONS_UPDATE", "name": "Update bot configurations", "module": "BOTS"},
{"code": "BOT_CONFIGURATIONS_DELETE", "name": "Delete bot configurations", "module": "BOTS"},
{"code": "BOT_CONFIGURATION_VERSIONS_READ", "name": "Read bot versions", "module": "BOTS"},
{"code": "BOT_CONFIGURATION_VERSIONS_WRITE", "name": "Write bot versions", "module": "BOTS"},
{"code": "BOT_TOOLS_READ", "name": "Read bot tools", "module": "BOTS"},
{"code": "BOT_TOOLS_WRITE", "name": "Write bot tools", "module": "BOTS"},
{"code": "BOT_STATE_READ", "name": "Read bot state", "module": "BOTS"},
{"code": "BOT_STATE_WRITE", "name": "Write bot state", "module": "BOTS"},
{"code": "BOT_EVENTS_READ", "name": "Read bot events", "module": "BOTS"},
{"code": "BOT_TOOL_CALLS_READ", "name": "Read bot tool calls", "module": "BOTS"},
{"code": "BOT_ENGINE_INVOKE", "name": "Invoke bot engine (debug)", "module": "BOTS"},
```

`ASESOR_PERMISSION_CODES` += `{MENU-BOTS, BOT_CONFIGURATIONS_READ, BOT_STATE_READ, BOT_EVENTS_READ, BOT_TOOL_CALLS_READ}`. `ADMIN_PERMISSION_CODES` los toma todos (ya filtra por código). DOCTOR sin cambios.

### Bot semilla (F3 — un seed de datos opcional, idempotente)

Un bot de demostración + su primera versión (provider=openai/`gpt-4.1-mini`) + las 6 tools crm/catalog + el M:N. Idempotente (`get_by_code` antes de insertar), corre tras los perms:

- `BotConfiguration(code="preventa", name="Bot Preventa", bot_type="preventa", max_turns_per_conversation=20)`.
- `BotConfigurationVersion(version=1, provider="openai", model_name="gpt-4.1-mini", system_prompt="<prompt de preventa en español>", parameters={"temperature":0.3,"max_tokens":500}, is_active=true)` → setear `current_version_id`.
- 6 `BotTool`: `list_verticals`/`list_services_by_vertical`/`list_products_by_vertical` (target `catalog.*.list_active`), `resolve_or_create_contact`/`register_lead_note`/`set_lead_status` (target `crm.*`), cada una con su `parameters_schema` (JSON Schema). `set_lead_status` con `requires_confirmation=true`.
- M:N: asociar las 6 tools al bot `preventa`.

> El bot semilla es opcional (útil para la demo + el smoke del dispatch). Las tools de scheduling (`book_appointment`/etc.) **NO se seedean** (su `target_service` apuntaría a `scheduling.*` inexistente → `TOOL_NOT_REGISTERED`). Las 6 tools MVP cargan en `TOOL_REGISTRY` al importar `engine.tools.crm`/`engine.tools.catalog` (los `@register_tool`).

---

## 13. Códigos de error (detalle ES + code EN + HTTP)

| code (EN) | HTTP | detail (ES) | Dónde |
|---|---|---|---|
| `BOT_CONFIGURATION_NOT_FOUND` | 404 | "Bot no encontrado" | configuration get/update/delete/activate-version; versions; tools M:N; engine |
| `BOT_CONFIGURATION_CODE_TAKEN` | 409 | "Ya existe un bot con el código '{code}'" | configuration create/update (guard unicidad) |
| `BOT_VERSION_NOT_FOUND` | 404 | "Versión no encontrada" | version get; activate-version |
| `BOT_VERSION_NOT_OWNED` | 400 | "La versión no pertenece a este bot" | activate-version (vid de otro bot) |
| `NO_CURRENT_VERSION` | 400 | "El bot no tiene versión vigente" | dispatch / activate sin versión vigente |
| `EXTERNAL_WEBHOOK_URL_REQUIRED` | 400 | "Se requiere la URL del webhook externo para el proveedor external_webhook" | version create (provider=external_webhook sin url) |
| `BOT_TOOL_NOT_FOUND` | 404 | "Tool no encontrada" | tool get/update/delete; set_config_tools (tool_id inexistente) |
| `BOT_TOOL_CODE_TAKEN` | 409 | "Ya existe una tool con el código '{code}'" | tool create (guard unicidad) |
| `TOOL_NOT_REGISTERED` | 404 | (runtime; result de la tool) | dispatch: target_service sin entrada en TOOL_REGISTRY |
| `PROVIDER_NOT_SUPPORTED` | 400 | "El proveedor '{provider}' no está soportado en esta versión" | engine_factory (provider sin adaptador en el MVP) |
| `BOT_STATE_NOT_FOUND` | 404 | "El bot no tiene estado en esta conversación" | state get / state/reset |
| `CONVERSATION_NOT_BOT` | 400 | "La conversación no está asignada a un bot" | dispatch sobre hilo no-bot; send_bot_outbound |
| `BOT_PROVIDER_ERROR` | — | (interno; log + BotEvent.error) | engine: el dispatch NO devuelve 5xx a Cloud Tasks salvo para forzar reintento |

> Excepciones de dominio del template (`app/core/exceptions.py`): `NotFoundException`(404), `AlreadyExistsException`(409), `BadRequestException`(400), `ForbiddenException`(403), `ConflictException`(409). El handler global traduce al envelope `{success:false, detail, code?, errors?}`. Los validators Pydantic (ej. `BotConfigurationVersionCreate._external_webhook_requires_url`, `min_length`) caen al 422 con `errors[]` y mensajes en inglés. `TOOL_NOT_REGISTERED`/`BOT_PROVIDER_ERROR` NO se surface como HTTP del dispatch (el turno los captura → `BotToolCall.error_message` / `BotEvent(turn_failed)` + fallback); aparecen como `code` solo en el dispatch-manual (debugging) o en las trazas.

---

## 14. Checklist de implementación (mapeado a fases F0–F3 + F4 diferida)

### F0 — Prep (sin migración; solo seed + skeleton)
- [ ] Agregar los 14 permisos `BOTS` a `app/core/seed.py:SEED_PERMISSIONS` (canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md)) + subset ASESOR read-only.
- [ ] Crear el skeleton `backend/app/modules/bots/{enums,models,schemas,repositories,services,routers}/` + `services/engine/{base,embedded,__init__,providers/{openai,claude},tools/{__init__,crm,catalog}}.py` (con `enums.py` completo + docstrings inertes). NO registrar en `app/modules/__init__.py` ni `main.py` todavía (lo cablea F1).
- [ ] Settings nuevos (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`BOT_DEFAULT_MODEL`/`MAX_TOOL_ITERATIONS_PER_TURN`/`CLOUD_TASKS_*`/`SERVICE_BASE_URL`/`BOT_DISPATCH_SECRET`, defaults vacíos).
- [ ] (Frontend F0) nav grupo "Bots" (`MENU-BOTS`: Configuraciones/Tools/Depuración) + `endpoints.ts` + `types/bots.types.ts` (espejo completo, inerte) — ver [`frontend.md`](frontend.md).
- [ ] Smoke: login admin → el JWT contiene los 14 permisos BOTS.

### F1 — BotConfiguration + Version + activate-version (migración `0017_bots_configuration`)
- [ ] `models/{bot_configuration,bot_configuration_version}.py` + `models/__init__.py` + migración `0017` (FKs circulares + **forward FK constraints aditivas** a channel_account/conversation).
- [ ] `schemas/{bot_configuration,bot_configuration_version}.py` (incl. `ActivateVersionRequest`; `BotConfigurationVersionCreate` valida external_webhook).
- [ ] `repositories/{bot_configuration,bot_configuration_version}.py` (`get_by_code`, `max_version`, `list_for_config`, `version_count_map`, ALLOWED_FIELDS solo columnas reales).
- [ ] `services/{bot_configuration,bot_configuration_version}.py` (CRUD + guard `BOT_CONFIGURATION_CODE_TAKEN` + `create` version max+1 + `activate_version` con `BOT_VERSION_NOT_OWNED`/`NO_CURRENT_VERSION`).
- [ ] Registrar `bots` en `app/modules/__init__.py` + aggregator router en `main.py`.
- [ ] `routers/bot_configuration.py` (CRUD + `/active` antes de `/{id}` + versions + activate-version).
- [ ] (Frontend F1) `/bots/configuraciones` (DataTable + drawer + tab de versiones + activar) — ver [`ui.md`](ui.md).
- [ ] Test: crear bot; `code` duplicado vivo → `409`; crear versión (version=1 → current automática); 2ª versión NO current; activate-version con vid de otro bot → `400 BOT_VERSION_NOT_OWNED`; external_webhook sin url → `400 EXTERNAL_WEBHOOK_URL_REQUIRED`.

### F2 — BotTool + M:N + TOOL_REGISTRY + tools crm/catalog (migración `0018_bots_tools`)
- [ ] `models/{bot_tool,associations}.py` + migración `0018` (bot_tool + M:N bot_configuration_tool).
- [ ] `schemas/bot_tool.py` (incl. `ConfigurationToolsUpdate`).
- [ ] `repositories/bot_tool.py` (`get_by_code`, `list_active`, `tool_ids_for_config`, `active_tools_for_config`, `set_config_tools`).
- [ ] `services/bot_tool.py` (CRUD + `set_config_tools` bulk M:N con `BOT_TOOL_NOT_FOUND`).
- [ ] `services/engine/tools/{__init__,crm,catalog}.py` (`TOOL_REGISTRY` + `@register_tool` + `BotInvocationContext`; tools crm/catalog reusando firmas reales).
- [ ] `routers/bot_tool.py` + endpoints `/configurations/{id}/tools` (GET + PUT bulk).
- [ ] (Frontend F2) `/bots/tools` (DataTable + drawer con JSON editor) + editor M:N de tools por bot — ver [`ui.md`](ui.md).
- [ ] Test: crear tool; `code` duplicado → `409`; set_config_tools con tool inexistente → `404`; el registry registra las 6 tools al importar; `is_registered=false` para una tool con target `scheduling.*`.

### F3 — Engine + State + Events + ToolCalls + Cloud Tasks + enganches conversations (migración `0019_bots_engine_state`)
- [ ] `models/{conversation_bot_state,bot_event,bot_tool_call}.py` + migración `0019` (input/output_message_id varchar(255) NO FK; trazas SIN deleted_at; UNIQUE conversation_id / (conversation_id, turn_number)).
- [ ] `schemas/{conversation_bot_state,bot_event,bot_tool_call,engine}.py` (incl. `DispatchTurnRequest`/`ResetBotStateRequest`).
- [ ] `repositories/{conversation_bot_state,bot_event,bot_tool_call}.py`.
- [ ] `services/engine/{__init__ (engine_factory),base,embedded (dispatch_turn + loop tool-calling),providers/{openai,claude}}.py` (adaptadores con `complete()`; import lazy de los SDK).
- [ ] **`app/core/cloud_tasks.py`** (cliente lazy + `enqueue_turn` OIDC; NO-OP en dev) + Settings + dep `google-cloud-tasks` + `openai` en `pyproject.toml`.
- [ ] **Enganches conversations** (aditivos): `message.send_bot_outbound` + hook bot en `find_or_create_open` + enqueue en `webhook_processor/whatsapp.process_inbound`.
- [ ] `services/{conversation_bot_state,bot_event,bot_tool_call}.py` (read-only depuración + reset_state).
- [ ] `routers/{conversation_bot_state,engine}.py` (`/state`/`state/reset`/`events`/`tool-calls`; `/engine/dispatch` OIDC + `/engine/dispatch-manual` RBAC).
- [ ] **Infra Cloud Tasks** (qa/prod): cola + IAM (`roles/cloudtasks.enqueuer` para la SA del servicio, `roles/run.invoker` para el invoker SA, `--no-allow-unauthenticated` en `/engine/dispatch`). Provider creds (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) en `--set-secrets`.
- [ ] (Frontend F3) panel de depuración por conversación (state + timeline BotEvent + tool calls) — ver [`ui.md`](ui.md).
- [ ] Test: `dispatch-manual` sobre un hilo `assignee_type='bot'` con bot+versión → `BotEvent(turn_started/completed)` + outbound del bot (sender_type='bot') + `ConversationBotState.turn_count++`; dispatch sobre hilo no-bot → `400 CONVERSATION_NOT_BOT`; bot sin versión → `400 NO_CURRENT_VERSION`; loop de tool-calling con una tool registrada → `BotToolCall(success)`; tool con target sin registry → `BotToolCall(error, TOOL_NOT_REGISTERED)`; provider external_webhook → `400 PROVIDER_NOT_SUPPORTED`; `state/reset` limpia slots + salta a la versión vigente; `max_turns_per_conversation` corta el turno. (Smoke: el adaptador del provider y las escrituras Firestore se mockean — el smoke valida el flujo del turno + las trazas, no la llamada real al LLM.)

### F4 — DIFERIDA
- [ ] `ExternalBotEngine` + endpoints `/engine/external/*` (provider=external_webhook; resuelve `external_webhook_secret_name` vía `secrets.resolve`).
- [ ] Tools scheduling (`book_appointment`/`check_availability`/`cancel_appointment`) tras #7 (`@register_tool` + seed).
- [ ] Handoff automático (`BotEventType.handoff_triggered` → `conversations.release` a unassigned/advisor cuando el bot detecta que necesita un humano).
- [ ] Streaming de la respuesta; cost cap duro (no solo `max_turns`); eval framework (golden conversations).

> Flujo de cada fase = la metodología: leer fichas → backend e2e + smoke (sqlite create_all, RESULT=PASS+conteo) → frontend e2e (subagente contexto fresco) → tsc+build → review adversaria (Workflow 4 dims → verificación por hallazgo) → commit limpio (sin Co-Authored-By) → ff develop→qa → QA E2E con limpieza → **gate usuario (AskUserQuestion separado del merge)** → prod → PROD read-only → actualizar memoria. Backend venv: `backend/.venv/Scripts/{python,ruff,mypy}.exe`.

---

## 15. Notas operativas (gotchas)

- **revid Alembic ≤ 32 chars** (clinic F3 reventó con 34 → StringDataRightTruncation). `0017_bots_configuration`=22, `0018_bots_tools`=15, `0019_bots_engine_state`=22. ✔
- **Glob NO ve `app/modules/**`** (OneDrive dehydration) → Read con paths exactos.
- **`BotEvent.input_message_id`/`output_message_id` = `varchar(255)` planos, NO FK** (no hay tabla message; ADR-011). El bot lee el contenido del mensaje de Firestore (`firestore.list_message_docs`).
- **`metadata` es reservado de SQLAlchemy** → atributo `event_metadata`, columna `"metadata"`; el schema lo expone como `metadata` (alias). Mismo cuidado en cualquier modelo con un campo "metadata".
- **FKs circulares `bot_configuration ↔ bot_configuration_version`**: crear ambas tablas sin la FK inline en la migración y agregarlas con `create_foreign_key` al final (sqlite/create_all tolera el `ForeignKey` inline del modelo porque crea ambas tablas en un solo `create_all`).
- **Forward FK constraints a conversations** (`channel_account`/`conversation`.`bot_configuration_id`) se cierran en `0017` con `ALTER TABLE ADD CONSTRAINT` Postgres-only (seguras: hoy todo NULL). NO agregar `relationship` ORM en conversations.
- **Import lazy de `openai`/`anthropic`/`google-cloud-tasks`** dentro de las funciones (no al import del módulo) → el boot/smoke sin las deps ni GCP no rompe. El smoke mockea el adaptador del provider + Firestore + Cloud Tasks.
- **`enqueue_turn` es NO-OP en dev** (`ENV_NAME=dev` / sin `CLOUD_TASKS_QUEUE`) → el smoke valida el pipe síncrono + el `assignee_type='bot'`, no Cloud Tasks. El dispatch se prueba vía `/engine/dispatch-manual` (RBAC `BOT_ENGINE_INVOKE`).
- **El dispatch NO devuelve 5xx a Cloud Tasks** salvo para forzar el reintento: un error de provider se captura como `BotEvent(turn_failed)` + mensaje de fallback (evita spamear al usuario con reintentos). Solo errores de infra recuperables (timeout transitorio) justifican re-raise.
- **El turno corre como SYSTEM** (`SYSTEM_USER_ID`, seed crm F0): trazas + tools llevan `created_by=SYSTEM`. Las tools NO reciben `CurrentAuth`; las reglas las impone el service de crm (matriz, dedup).
- **`send_bot_outbound` valida `assignee_type=='bot'`** (NO advisor-assignee check). El relay síncrono del outbox lo dispara el ROUTER de dispatch (igual que el composer/webhook de conversations — evita el ciclo de import con `conversation`).
- **PowerShell 5.1**: no `&&`, `$pid` reservado (usar `$srvPid`), no `-SkipHttpErrorCheck`, IWR cuelga→curl.
- **TZ**: `last_bot_turn_at`/`started_at` tz-aware UTC (`utc_now()`); el render de "Hace N min" + day-groups de la timeline de depuración va client-only (lección TZ recurrente).
- **`app/modules/__init__.py`**: incluir `bots` en F1 (para que Alembic/relationships lo registren). En F0 el skeleton es inerte (NO registrado).
- **1 comando por call** en git/deploy; verificar que el verificador CORRIÓ (RESULT=PASS + conteo); gate de prod = AskUserQuestion separado del merge.

---

## 16. Decisiones para ADRs / consolidación

- **ADR-005 (REVISAR, mantener Accepted, "act. 2026-06-04")**: el ADR original (2026-05-28) es PRE-Firestore/CQRS, PRE-Cloud-Tasks y PRE-orden-real. Actualizar con: (a) **Mensajes en Firestore** (ADR-011) → `BotEvent.input/output_message_id` = `mid` Firestore varchar(255), NO FK; el bot lee el historial de Firestore; (b) **Async = Cloud Tasks** (ADR-012), NO BackgroundTasks/síncrono; (c) **Embedded multi-proveedor** (OpenAI default `gpt-4.1-mini` + Claude), `ExternalBotEngine` DISEÑADO pero DIFERIDO (campos sin impl); (d) **Tools = crm + catalog SOLO** (scheduling diferido); (e) **enganches conversations** aditivos (`send_bot_outbound`, hook bot en `find_or_create_open`, enqueue en el webhook); (f) credenciales provider = `Settings.OPENAI_API_KEY`/`ANTHROPIC_API_KEY` globales (resolución per-bot vía secret_resolver = futuro); (g) guards `MAX_TOOL_ITERATIONS_PER_TURN`/`max_turns_per_conversation`.
- **ADR-012 (NUEVO, Accepted, 2026-06-04)**: "Cloud Tasks dispatch del turno del bot". **Context**: el turno llama a un LLM (segundos + loops de tool-calling) = trabajo lento must-complete; BackgroundTasks no sobrevive el apagado de la instancia ni la CPU throttling post-response de Cloud Run, sin reintentos. **Decision**: el webhook (tras su pipe síncrono) encola una Cloud Task → `POST /api/v1/bots/engine/dispatch` (OIDC, sin RBAC, CPU asignada) corre `dispatch_turn`; reintentos+backoff+DLQ+rate-limit los da la cola. `app/core/cloud_tasks.py` (cliente lazy + `enqueue_turn`, molde `secrets.py`/`firestore.py`). **Alternatives**: BackgroundTasks (RECHAZADA: no durable, CPU throttled); síncrono en el webhook (RECHAZADA: Meta timeout + bloquea el ack); Pub/Sub (viable, descartada a favor de Cloud Tasks por el target HTTP directo + OIDC nativo). **Consequences**: durabilidad + reintentos + CPU; complejidad (cola + IAM invoker SA + endpoint interno OIDC). Referencia a ADR-005 (revisado) y ADR-011.
- **Diagramas**: regenerar `er-bots.puml` (7 entidades + M:N `bot_configuration_tool`; `channel_account`/`conversation`/`person`/`vertical` como external punteados; `bot_event.input/output_message_id` anotado "mid Firestore, NO FK"; las 2 forward FK constraints a conversations) + `class-backend-bots.puml` (modelos + repos + services + el **engine package**: `BotEngine`/`EmbeddedBotEngine`/`engine_factory`/adaptadores `OpenAIProvider`/`ClaudeProvider`/`TOOL_REGISTRY`/`BotInvocationContext`/tools crm·catalog; `app/core/cloud_tasks.py`; los enganches conversations consumidos). Índice `docs/diagrams/README.md`.
- **Overview viejo**: borrar `docs/modules/bots.md` (consolidado en el README) y repuntar TODOS sus links (`grep "modules/bots.md"`) al `bots/README.md`.
- **Memoria**: crear/actualizar `project_medisage_bots_plan.md` + puntero en MEMORY.md.
