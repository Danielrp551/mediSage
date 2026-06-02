# Módulo `conversations` — Backend deep-dive

> **Última actualización**: 2026-06-02
> **Audiencia**: developer implementando `backend/app/modules/conversations/` + el router top-level nuevo `backend/app/routers/webhooks.py` + el cross-cutting `backend/app/core/secrets.py`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`../../decisions/ADR-004-conversation-channel-account.md`](../../decisions/ADR-004-conversation-channel-account.md) (Conversation + ChannelAccount, **se actualiza en esta fase**), [`../../decisions/ADR-009-forward-fk-deferred-cross-module.md`](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (FKs forward diferidas), [`../../decisions/ADR-010-runtime-secret-resolution.md`](../../decisions/ADR-010-runtime-secret-resolution.md) (resolución de secretos por-cuenta en runtime — **nuevo**), [`_seed-and-roles.md`](../_seed-and-roles.md) (los 12 permisos `CONVERSATIONS` + roles `ASESOR`/`DOCTOR`/`ADMIN`), y los deep-dives molde [`../crm/backend.md`](../crm/backend.md) (gold-standard: denormalización batch sin N+1, `find_by_identifier_or_create`, `lead_activity.log`, ADR-009, migraciones manuales) y [`../staff/backend.md`](../staff/backend.md) (`/me`, helpers aditivos a `admin`).

> **Contrato autoritativo**: este doc respeta la **spec compartida de `conversations`** (`C:/tmp/conversations_spec.md` durante la fase de documentación; luego consolidada en [`README.md`](README.md)). Los nombres EXACTOS de entidades/campos/endpoints/permisos/códigos-de-error/enums/fases salen de ahí. Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc.

> **Convenciones heredadas de `catalog`/`clinic`/`staff`/`crm` shipped** (repetidas aquí para que este doc se lea solo):
>
> 1. **`PUT` para updates completos** (no `PATCH`). El ADR-004 viejo usaba `PATCH` — **deprecado**, reemplazado por `PUT` en TODA la ficha.
> 2. **`/active` para dropdowns** → **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`), igual que `catalog`/`clinic`/`staff`/`crm`.
> 3. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `AlreadyExistsException`, `BadRequestException`, `ForbiddenException`, `ConflictException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; reload-via-`get_full`/`get_by_id` tras create/update (relaciones `lazy="raise"`); `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` como whitelist estricta (los campos denormalizados NO son server-sortable/filterable — búsqueda por ellos = client-side; **lección hotfix `cd10c78` de `staff`**).
> 4. **Mensajes `detail` de dominio en español, `code` en inglés**; mensajes de validators Pydantic en inglés (van al detalle 422; el front re-valida con Zod y muestra copy en español). UI 100% español.
> 5. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), lista cruda en `/active`, error `{success:false, detail, code?, errors?}`.
> 6. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `conversations` arranca en `0015` (última aplicada = `0014_crm_customer_lifecycle`).
> 7. Patrón **audit users**: `created_by`/`updated_by` explícitos; `*_user: UserAuditInfo | None` hidratado vía `user_repository.get_audit_info_map` batch (sin N+1).
> 8. **Mixins del template** (`app.shared.base_model`): `PrimaryKeyMixin` (`id` varchar(36)), `ActiveMixin` (`active`), `SoftDeleteMixin` (`deleted_at`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **`Message`/`MessageAttachment`/`ConversationAssignmentLog` NO llevan `SoftDeleteMixin`** — son audit trail honesto (mensajes inmutables, historial de handoff inmutable); "borrar" un log no es una operación de negocio.

`conversations` es el **módulo #5** de medisage (catalog→clinic→staff→crm **COMPLETOS en prod**; sigue conversations; luego bots #6, scheduling #7, marketing #8). Es el **dueño del pipe de mensajería multicanal**: recibe inbound desde webhooks de proveedores (WhatsApp Cloud API en el MVP), valida la firma, persiste, identifica al `Person` vía `crm.find_by_identifier_or_create`, auto-asigna la conversación al dueño del lead y la deja en la bandeja del asesor; del lado saliente envía mensajes reales contra Meta Graph API. Decisiones nuevas que este doc materializa: **ADR-010** (resolución de secretos por-cuenta vía Secret Manager SDK en runtime, cacheado) y **ADR-004 actualizado**.

---

## 1. Estructura de archivos a crear

```
backend/app/
├── core/
│   └── secrets.py                        # NUEVO cross-cutting: secret_resolver (SDK Secret Manager + cache TTL + fallback env)  ── F1
├── routers/                              # NUEVO paquete top-level (hoy NO existe app/routers/)
│   ├── __init__.py                       # docstring; no aggregator (cada router top-level se incluye suelto en main.py)
│   └── webhooks.py                       # router top-level SIN JWT: GET verify + POST inbound de WhatsApp  ── F2
└── modules/conversations/
    ├── __init__.py
    ├── enums.py                          # ConversationStatus, AssigneeType, MessageDirection, SenderType, ContentType, AttachmentType, MessageExternalStatus
    ├── models/
    │   ├── __init__.py                   # importa todos los modelos (registro en Base.metadata)
    │   ├── channel_account.py            # ── F1
    │   ├── conversation.py               # ── F2
    │   ├── message.py                    # ── F2
    │   ├── message_attachment.py         # ── F2 (modelado; processing diferido F4)
    │   └── conversation_assignment_log.py # ── F2
    ├── schemas/
    │   ├── __init__.py
    │   ├── channel_account.py            # ChannelAccountCreate/Update/Item/Detail/Option  (Detail NUNCA expone el secreto)
    │   ├── conversation.py               # ConversationListItem, ConversationDetail, Take/Release requests, ConversationAssignmentLogItem
    │   └── message.py                    # MessageItem, MessageAttachmentItem, MessageSendRequest
    ├── repositories/
    │   ├── __init__.py
    │   ├── channel_account.py            # get_by_external_id, list/active
    │   ├── conversation.py               # get_open, find/list_inbox, ALLOWED_FIELDS, denorm batch maps
    │   ├── message.py                    # get_by_external_id, append, list_for_conversation
    │   ├── message_attachment.py         # list_for_messages (batch)
    │   └── conversation_assignment_log.py # current_open, list_for_conversation, close_current/open_new
    ├── services/
    │   ├── __init__.py
    │   ├── channel_account.py            # CRUD + get_credentials(ca) (delega a app.core.secrets / fallback env)
    │   ├── conversation.py               # find_or_create_open (auto-asignación), take/release/close/reopen/mark_read
    │   ├── message.py                    # persist_inbound, send_outbound (Meta Graph API), apply_status
    │   └── webhook_processor/
    │       ├── __init__.py
    │       └── whatsapp.py               # verify_signature, process_inbound, process_status (cohesión por canal)
    └── routers/
        ├── __init__.py                   # aggregator: prefix="/conversations"
        ├── channel_account.py            # /channel-accounts/*
        ├── conversation.py               # /list, /{id}, take/release/close/reopen/mark-read, /messages/*
        └── me.py                         # /me/conversations/list
```

> **Sin `models/associations.py`**: `conversations` no introduce M:N nuevas. `ConversationAssignmentLog` es una **entidad** (PK propia, mixins, audit), no una tabla de asociación.
> **El `webhook_processor` es un sub-paquete de `services`** (cohesión por dominio): el router top-level `app/routers/webhooks.py` solo valida la firma y delega a `webhook_processor/whatsapp.py`. Un canal nuevo (telegram) = un módulo nuevo `webhook_processor/telegram.py`, sin tocar el router (despacho por `channel_account.channel_type`).

### 1.1 Registro del módulo

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean) — **incluir `conversations` aunque `staff` no esté** (tolerado por las migraciones manuales; ver gotcha §14 de la spec):

```python
from app.modules import admin, catalog, clinic, conversations, crm, staff  # noqa: F401
```

Y registrar **dos** routers en `app/main.py` (el aggregator autenticado del módulo **y** el router top-level de webhooks):

```python
from app.modules.conversations.routers import router as conversations_router
from app.routers.webhooks import router as webhooks_router

# ── Routers ───────────────────────────────────────
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog_router, prefix=settings.API_V1_PREFIX)
app.include_router(clinic_router, prefix=settings.API_V1_PREFIX)
app.include_router(conversations_router, prefix=settings.API_V1_PREFIX)  # /conversations interno
app.include_router(crm_router, prefix=settings.API_V1_PREFIX)
app.include_router(staff_router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks_router, prefix=settings.API_V1_PREFIX)        # /webhooks/whatsapp/...  (SIN JWT)
```

> Ambos se montan bajo `settings.API_V1_PREFIX` (`/api/v1`). El aggregator del módulo añade `/conversations`; `webhooks_router` añade `/webhooks` directamente. **El módulo se registra en F1** (con el aggregator que solo expone `/channel-accounts/*`); **el `webhooks_router` se registra en F2** (cuando existe el processor).

El aggregator `routers/__init__.py` replica el patrón de `crm/routers/__init__.py`:

```python
"""
Aggregates the conversations sub-routers under one prefix. `main.py` includes this
`router` once. Order matters only inside each sub-router (/active before /{id});
the aggregator order is informational. The webhooks router is TOP-LEVEL (no JWT) and
lives in app/routers/webhooks.py — NOT here.
"""

from fastapi import APIRouter

from app.modules.conversations.routers.channel_account import router as channel_account_router
from app.modules.conversations.routers.conversation import router as conversation_router
from app.modules.conversations.routers.me import router as me_router

router = APIRouter(prefix="/conversations")
router.include_router(channel_account_router)  # /channel-accounts/*
router.include_router(conversation_router)     # /list, /{id}, take/release/close/reopen/mark-read, /messages/*
router.include_router(me_router)               # /me/conversations/list

__all__ = ["router"]
```

> **`/me/conversations` y el prefix**: el `me_router` declara `prefix="/me/conversations"`; combinado con el aggregator queda `/api/v1/conversations/me/conversations/list`. Es el shape de la spec §7 (consistente con crm `/me/leads/list` = `/api/v1/crm/me/leads/list`). El `/me` resuelve el asesor desde `CurrentAuth`, no necesita perfil especial.

---

## 2. Enums — `enums.py` (en código, NO en BD)

`StrEnum` (ruff UP042) — contratos estables del código, no catálogos en BD. Las columnas que los referencian son `varchar` planas; Pydantic valida contra el enum, la BD almacena el slug.

> **`ChannelType` se REUSA de `crm.enums`** (single source of truth — el docstring de `crm.enums` ya dice "the slug crosses with conversations.ChannelAccount.channel_type"). `conversations` hace `from app.modules.crm.enums import ChannelType`. **NO duplicar.** Valores: `whatsapp`/`telegram`/`web`/`phone`/`email`/`instagram`/`facebook`/`other` (MVP usa `whatsapp`).

```python
"""
conversations enums. NONE of these are DB catalogs — they are code-level value sets.
ChannelType is NOT redefined here — it is REUSED from crm.enums (single source of
truth; the slug crosses with crm.PersonContactIdentifier.channel_type). The columns
that reference these are plain varchar; Pydantic validates, the DB stores the slug.
"""

from __future__ import annotations

from enum import StrEnum

# NB: ChannelType is imported from crm — `from app.modules.crm.enums import ChannelType`.


class ConversationStatus(StrEnum):
    open = "open"
    closed = "closed"


class AssigneeType(StrEnum):
    bot = "bot"
    advisor = "advisor"
    unassigned = "unassigned"


class MessageDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class SenderType(StrEnum):
    contact = "contact"
    bot = "bot"
    advisor = "advisor"
    system = "system"


class ContentType(StrEnum):
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"
    document = "document"
    location = "location"
    sticker = "sticker"
    contact_card = "contact_card"
    system_notification = "system_notification"


class AttachmentType(StrEnum):
    image = "image"
    audio = "audio"
    video = "video"
    document = "document"
    location = "location"
    sticker = "sticker"
    contact_card = "contact_card"


class MessageExternalStatus(StrEnum):
    """Known values of message.external_status. The column itself is free varchar
    (the provider may return others); this enum is the contract for the UI badges."""

    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"
```

> **`MESSAGE_SENT`/`CONVERSATION_TAKEN`/`CONVERSATION_RELEASED`** NO son enums de conversations: son valores de `crm.enums.ActivityType` (ya declarados completos en crm desde el inicio). conversations los emite a la timeline de crm vía `crm.lead_activity.log` (ver §6). En el MVP conversations emite **solo** `CONVERSATION_TAKEN` y `CONVERSATION_RELEASED`; `MESSAGE_SENT` queda en el enum de crm para un uso futuro.

---

## 3. Models — SQLAlchemy 2.0

> ⚠ **Columnas forward (`bot_configuration_id`, `default_campaign_id`) son `mapped_column(String(36), nullable=True, index=True)` SIN `ForeignKey` ni `relationship`.** Las tablas `bot_configuration`/`campaign` aún NO existen; declarar el FK rompería el mapper al importar. El módulo dueño (`bots` #6 / `marketing` #8) agrega la `FK CONSTRAINT` + `relationship` de forma aditiva. Patrón documentado en **ADR-009**. Hoy ambas SIEMPRE NULL.
> ⚠ **FKs reales** (`channel_account.id`, `person.id`, `user.id`) SÍ llevan `ForeignKey(...)` — `conversations`, `crm` y `admin` ya existen.
> ⚠ **UNIQUE parciales dialect-agnósticos**: `Index(..., unique=True, postgresql_where=text(...), sqlite_where=text(...))` — el `sqlite_where` espeja el `postgresql_where` para que el smoke (`create_all` en sqlite, no alembic) reproduzca el índice parcial (mismo patrón real que `crm.person_contact_identifier`/`crm.lead_assignment`). Sin el `sqlite_where`, el test "una sola open + reabrir" fallaría en sqlite.
> ⚠ **JSONB variant**: `provider_payload`/`metadata` usan `JSON().with_variant(JSONB(), "postgresql")` (idéntico a `crm.lead_activity.payload`): JSONB en Postgres (prod), JSON en sqlite (el smoke usa `create_all`, no alembic; JSONB puro no serializa dicts en sqlite). La migración escribe `JSONB` (solo corre en Postgres).

### `models/channel_account.py` — tabla `channel_account` — PK·A·SD·T

```python
"""
ChannelAccount = una cuenta de canal de la clínica (config + referencia al secreto).
Multi-cuenta: N números de WhatsApp sin redeploy (cada uno con su secret_name). El
SECRETO NUNCA vive en BD ni se expone en la API — secret_name apunta a GCP Secret
Manager y el secret_resolver lo resuelve en runtime (ADR-010). channel_type es el
valor de crm.ChannelType (reuse; NO un FK a un catálogo). bot_configuration_id /
default_campaign_id son FKs forward (ADR-009): varchar(36)+index, SIN FK/relationship.
"""

from __future__ import annotations

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class ChannelAccount(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "channel_account"
    __table_args__ = (
        # Partial UNIQUE: a LIVE (channel_type, external_identifier) is globally unique
        # (single-tenant). After soft-delete the pair frees up for re-registration.
        Index(
            "uq_channel_account_type_external",
            "channel_type",
            "external_identifier",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)  # crm.ChannelType (reuse)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    # Reference to the per-account secret in GCP Secret Manager (resolved at runtime).
    # NULL = fallback to env (local/dev). The SECRET itself is never stored here.
    secret_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Meta verification challenge token (GET webhook). Not a hard secret (Meta sends
    # it and we compare) → plain column, editable by admin.
    webhook_verify_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # WhatsApp Cloud API phone number id → builds the send URL /{phone_number_id}/messages.
    phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Forward FK to bots.bot_configuration (ADR-009) — default bot of the channel. Today NULL.
    bot_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Forward FK to marketing.campaign (ADR-009) — attribution campaign passed to
    # find_by_identifier_or_create(campaign_id=...). Today NULL.
    default_campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
```

### `models/conversation.py` — tabla `conversation` — PK·A·SD·T

```python
"""
Conversation = un hilo Person ↔ ChannelAccount. INVARIANTE central: a lo sumo UN hilo
abierto por (person_id, channel_account_id) — UNIQUE PARCIAL WHERE status='open' AND
deleted_at IS NULL. Cerrar = status='closed' (la fila no se soft-deletea; queda como
historial; reabrir valida que no haya otra open). assignee_user_id es FK real a user;
NOT NULL ⟺ assignee_type='advisor' (invariante de service, no de BD). last_message_at/
preview/unread_count son denormalizados para la bandeja (inbox).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Conversation(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = (
        # At most ONE open conversation per (person, channel) — the dedup that makes
        # find_or_create_open deterministic. Partial: closed/soft-deleted rows free it.
        Index(
            "uq_conversation_person_channel_open",
            "person_id",
            "channel_account_id",
            unique=True,
            postgresql_where=text("status = 'open' AND deleted_at IS NULL"),
            sqlite_where=text("status = 'open' AND deleted_at IS NULL"),
        ),
    )

    channel_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channel_account.id"), nullable=False, index=True
    )
    # FK real → person.id (crm existe). NULL solo en la ventana corta antes de resolver
    # (en práctica siempre poblado tras find_or_create_open).
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ConversationStatus
    assignee_type: Mapped[str] = mapped_column(String(20), nullable=False)  # AssigneeType
    # FK real → user.id. NOT NULL ⟺ assignee_type='advisor' (invariante de service).
    assignee_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True, index=True
    )
    # Forward FK to bots.bot_configuration (ADR-009) — bot efectivo. Hoy NULL.
    bot_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Denormalized for the inbox (sort + preview + badge).
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

> **`status='closed'` NO soft-deletea la conversación.** Cerrar es un estado de negocio (la conversación queda en el historial; el deep-link `?status=closed` la lista; reabrir la vuelve a abrir). El `deleted_at` queda para una eliminación lógica real (rara). Por eso el UNIQUE parcial filtra por `status='open' AND deleted_at IS NULL`: una persona puede tener N conversaciones cerradas en el mismo canal pero a lo sumo una abierta. **Sutileza sqlite**: el `sqlite_where` con la comparación de string (`status = 'open'`) reproduce el índice parcial en el smoke.
> **Invariantes (validados en el service, code propio — NO en la BD)**:
> - `assignee_type='advisor'` ⇒ `assignee_user_id NOT NULL` (sino `INVALID_ASSIGNEE` 400).
> - `assignee_type ∈ {bot, unassigned}` ⇒ `assignee_user_id IS NULL`.
> - `assignee_type='bot'` ⇒ `bot_configuration_id NOT NULL` (no aplica en MVP — bots no existe).
> - Cerrar (status='closed') ⇒ cierra el `ConversationAssignmentLog` vigente (`ended_at=now`).
> - Cambio de assignee ⇒ cierra el log vigente + abre uno nuevo (misma tx).

### `models/message.py` — tabla `message` — PK·A·T (SIN SoftDelete — audit inmutable)

```python
"""
Message = un mensaje inmutable de una Conversation. SIN SoftDeleteMixin (audit trail
honesto — un mensaje enviado/recibido no se borra). direction/sender_type/content_type
son los enums. external_id es el id en el proveedor (WA wamid / Telegram message_id);
UNIQUE PARCIAL (conversation_id, external_id) WHERE external_id IS NOT NULL para
idempotencia ante el reenvío del webhook de Meta. sender_user_id es FK real a user;
NOT NULL ⟺ sender_type='advisor'. provider_payload guarda el payload original (debug).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class Message(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "message"
    __table_args__ = (
        # Idempotency: a provider message id is unique within a conversation. Partial
        # so outbound rows pre-send (external_id NULL) don't collide. NULLs excluded.
        Index(
            "uq_message_conversation_external",
            "conversation_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
            sqlite_where=text("external_id IS NOT NULL"),
        ),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # MessageDirection
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SenderType
    # FK real → user.id. NOT NULL ⟺ sender_type='advisor' (invariante de service).
    sender_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    # Forward FK to bots.bot_configuration (ADR-009). Hoy NULL.
    bot_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ContentType
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # WA wamid / etc.
    external_status: Mapped[str | None] = mapped_column(String(40), nullable=True)  # free; ver enum
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Original provider payload (debug). JSON en sqlite (smoke), JSONB en Postgres.
    provider_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
```

### `models/message_attachment.py` — tabla `message_attachment` — PK·A·T (SIN SoftDelete) — modelado, processing diferido (F4)

```python
"""
MessageAttachment = un adjunto de un Message (media). SIN SoftDeleteMixin (audit). La
tabla se CREA en la migración de threads (F2) para no re-migrar, pero el processor
F2/F3 NO la puebla (decisión "texto primero"): inbound/outbound de media se cablea en
F4 (download/storage — lazy proxy vs GCS se re-confirma al llegar). external_media_id
es el id del medio en el proveedor (para el download diferido). metadata = JSONB variant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class MessageAttachment(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "message_attachment"

    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("message.id"), nullable=False, index=True
    )
    attachment_type: Mapped[str] = mapped_column(String(20), nullable=False)  # AttachmentType
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # storage decision = F4
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)   # location
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)  # location
    address_label: Mapped[str | None] = mapped_column(String(255), nullable=True)  # location
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_media_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # provider media id
    attachment_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
```

> ⚠ **`metadata` es atributo reservado en la `Base` declarativa de SQLAlchemy** (`Base.metadata` es el `MetaData`). El atributo Python se llama `attachment_metadata` pero la **columna** se nombra `"metadata"` (primer posicional de `mapped_column`) para que el contrato BD/JSON sea `metadata`. El schema `MessageAttachmentItem` expone `metadata` (alias en Pydantic o `model_validate` desde `attachment_metadata`). **Nota de fase**: NULL en el MVP (texto primero); F4 lo puebla.

### `models/conversation_assignment_log.py` — tabla `conversation_assignment_log` — PK·A·T (SIN SoftDelete — audit inmutable)

```python
"""
ConversationAssignmentLog = historial INMUTABLE de handoff de una Conversation (quién
la tuvo, cuándo, quién hizo el cambio). SIN SoftDeleteMixin. A lo sumo UNA fila vigente
(ended_at IS NULL) por conversación — la cierra el siguiente take/release/close. NO se
modela como UNIQUE parcial: el invariante "una sola vigente" lo garantiza el service
(close_current antes de open_new, misma tx). from_* es NULL en el primer log. Las FKs a
user son reales; by_actor_user_id NULL = cambio automático (sistema).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class ConversationAssignmentLog(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "conversation_assignment_log"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    from_assignee_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # NULL primer log
    from_assignee_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    to_assignee_type: Mapped[str] = mapped_column(String(20), nullable=False)  # AssigneeType
    to_assignee_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # NULL=vigente
    # FK real → user.id. NULL = cambio automático (sistema / auto-asignación).
    by_actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### `models/__init__.py`

```python
"""
Importing models here registers them on Base.metadata before Alembic reads the schema
and before string-based relationship() resolution runs. Order: parents (channel_account)
before children (conversation → message → message_attachment, conversation_assignment_log).
"""

from app.modules.conversations.models.channel_account import ChannelAccount
from app.modules.conversations.models.conversation import Conversation
from app.modules.conversations.models.message import Message
from app.modules.conversations.models.message_attachment import MessageAttachment
from app.modules.conversations.models.conversation_assignment_log import (
    ConversationAssignmentLog,
)

__all__ = [
    "ChannelAccount",
    "Conversation",
    "Message",
    "MessageAttachment",
    "ConversationAssignmentLog",
]
```

> **Lazy strategy**: NO se declaran `relationship(...)` cross-módulo (a `Person`/`User`) — consistente con el patrón crm "sin relationship cross-módulo, todo por FK column + batch maps". Dentro del módulo tampoco se declaran relationships (los hijos se consultan por `conversation_id`/`message_id` directamente y se denormalizan vía batch maps), para mantener el modelo plano y los reads explícitos (sin N+1 silencioso). `ConversationDetail.assignment_history` y `MessageItem.attachments` se arman con queries de repo dedicadas, no con lazy-load.

---

## 4. Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (idénticas a crm/staff): (1) no usar Ellipsis (`...`) en `Field(...)`; (2) `Annotated` solo para `Query`/`Path` en routers; (3) validators `@field_validator` single-field, `@model_validator(mode="after")` cross-field; (4) mensajes de validator en inglés (van al 422); copy user-facing en español en el Zod del front; (5) `model_config = ConfigDict(from_attributes=True)` en los `*Item`/`*Detail`/`*Option`.

### `schemas/channel_account.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType  # REUSE


class ChannelAccountCreate(BaseModel):
    channel_type: ChannelType
    name: str = Field(min_length=1, max_length=120)
    external_identifier: str = Field(min_length=1, max_length=255)
    secret_name: str | None = Field(default=None, max_length=255)
    webhook_verify_token: str | None = Field(default=None, max_length=255)
    phone_number_id: str | None = Field(default=None, max_length=64)
    # bot_configuration_id / default_campaign_id NO se exponen en el MVP (forward FKs,
    # siempre NULL; los expondrá bots/marketing).


class ChannelAccountUpdate(BaseModel):
    """Partial. channel_type/external_identifier ARE editable (corregir un alta) pero
    re-disparan el guard de unicidad. El SECRETO no se gestiona acá."""

    channel_type: ChannelType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    external_identifier: str | None = Field(default=None, min_length=1, max_length=255)
    secret_name: str | None = Field(default=None, max_length=255)
    webhook_verify_token: str | None = Field(default=None, max_length=255)
    phone_number_id: str | None = Field(default=None, max_length=64)
    active: bool | None = None


class ChannelAccountOption(BaseModel):
    """Dropdown / filtro shape — GET /channel-accounts/active (raw list). Lo consume el
    inbox (chip de canal) y los espejos en ConversationListItem.channel_account."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    channel_type: ChannelType
    external_identifier: str


class ChannelAccountItem(BaseModel):
    """Row de la tabla /channel-accounts/list."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    channel_type: ChannelType
    name: str
    external_identifier: str
    phone_number_id: str | None
    # NUNCA el secreto: solo si está configurado (secret_name set) + si Meta puede verificar.
    has_secret: bool                  # = secret_name is not None
    has_verify_token: bool            # = webhook_verify_token is not None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class ChannelAccountDetail(ChannelAccountItem):
    """Full para el drawer de edición. EXPONE `secret_name` (el NOMBRE del secreto, NO
    su valor) y `webhook_verify_token` (no es secreto duro: lo envía Meta y se compara).
    NUNCA expone access_token/app_secret — esos viven solo en Secret Manager y los
    resuelve get_credentials server-side."""

    secret_name: str | None
    webhook_verify_token: str | None
    bot_configuration_id: str | None = None
    default_campaign_id: str | None = None
```

> **`ChannelAccountDetail` NUNCA expone el secreto.** El `access_token`/`app_secret` viven solo en GCP Secret Manager; el API expone `secret_name` (el nombre del recurso) + los flags `has_secret`/`has_verify_token`. `get_credentials(ca)` (server-only) es el único camino al valor. El frontend muestra "configurado / sin configurar" (no el valor). `webhook_verify_token` SÍ se expone porque no es un secreto duro (Meta lo envía en claro en el GET de verificación y solo lo comparamos).

### `schemas/message.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.enums import (
    AttachmentType,
    ContentType,
    MessageDirection,
    SenderType,
)


class MessageAttachmentItem(BaseModel):
    """Shape de message_attachment (presente en el contrato; sin processing en el MVP →
    en la práctica lista vacía hasta F4)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    message_id: str
    attachment_type: AttachmentType
    url: str | None
    mime_type: str | None
    size_bytes: int | None
    duration_sec: int | None
    latitude: float | None
    longitude: float | None
    address_label: str | None
    original_filename: str | None
    external_media_id: str | None
    metadata: dict | None = None  # se hidrata desde attachment_metadata en el service


class MessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    direction: MessageDirection
    sender_type: SenderType
    sender_user_id: str | None              # raw FK lógica (advisor)
    sender_user: UserAuditInfo | None = None  # denormalized; null para contact/bot/system
    content_type: ContentType
    content: str | None
    external_id: str | None
    external_status: str | None             # free varchar; la UI mapea a MessageExternalStatus
    sent_at: datetime
    delivered_at: datetime | None
    read_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None
    attachments: list[MessageAttachmentItem] = Field(default_factory=list)
    created_on: datetime


class MessageSendRequest(BaseModel):
    """Body de POST /conversations/{id}/messages. MVP solo text → el validator rechaza
    otros con 422 (el service además puede levantar UNSUPPORTED_CONTENT_TYPE 400);
    attachments en F4."""

    content: str = Field(min_length=1, max_length=4096)
    content_type: ContentType = ContentType.text

    @model_validator(mode="after")
    def _text_only_mvp(self) -> "MessageSendRequest":
        if self.content_type != ContentType.text:
            raise ValueError("only text content_type is supported in the MVP")
        return self
```

### `schemas/conversation.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.enums import AssigneeType, ConversationStatus
from app.modules.conversations.schemas.channel_account import ChannelAccountOption
from app.modules.crm.schemas.person import PersonOption  # denormalizado vía batch map de crm


class ConversationListItem(BaseModel):
    """Row del inbox. Optimizado para la lista 2-paneles: person denormalizado vía batch
    map de crm; channel denormalizado; assignee resuelto a UserAuditInfo. last_message_*
    + unread_count son columnas reales de conversation."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    channel_account: ChannelAccountOption
    person: PersonOption | None = None
    status: ConversationStatus
    assignee_type: AssigneeType
    assignee_user: UserAuditInfo | None = None
    last_message_preview: str | None
    last_message_at: datetime | None
    unread_count: int
    created_on: datetime


class ConversationAssignmentLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    from_assignee_type: AssigneeType | None = None
    from_assignee_user: UserAuditInfo | None = None
    to_assignee_type: AssigneeType
    to_assignee_user: UserAuditInfo | None = None
    started_at: datetime
    ended_at: datetime | None
    by_actor_user: UserAuditInfo | None = None
    reason: str | None


class ConversationDetail(ConversationListItem):
    """Extiende ListItem con la config completa + el historial de handoff."""

    bot_configuration_id: str | None = None
    opened_at: datetime
    closed_at: datetime | None
    assignment_history: list[ConversationAssignmentLogItem] = Field(default_factory=list)


class TakeConversationRequest(BaseModel):
    """Body de POST /conversations/{id}/take."""

    reason: str | None = Field(default=None, max_length=255)


class ReleaseConversationRequest(BaseModel):
    """Body de POST /conversations/{id}/release. to_assignee_type ∈ {bot, unassigned}
    en el MVP (advisor = take). to_bot_configuration_id solo si bots existiera (hoy
    ignorado/NULL)."""

    to_assignee_type: AssigneeType
    to_bot_configuration_id: str | None = Field(default=None, max_length=36)
    reason: str | None = Field(default=None, max_length=255)
```

> **`PersonOption` se reusa de `crm.schemas.person`** (`{id, full_name, document_number, primary_identifier}`) — `conversations` no redefine el shape de la persona; lo denormaliza vía un batch map de crm (ver §5). `UserAuditInfo` de `admin.schemas.audit` (igual que crm). El detalle de excepción va en español; los mensajes de validator Pydantic en inglés (422); el copy user-facing en español vive en el Zod del front.

---

## 5. Repositories

`ALLOWED_FIELDS` = whitelist de columnas filtrable/ordenable desde el frontend. **Lección hotfix `cd10c78` de `staff`**: solo columnas **reales** de la tabla — nunca campos denormalizados (ordenar/filtrar por ellos da 400). Los deep-links por `*_id` los traduce el **service** a filtros sobre columnas reales (mismo patrón que `crm.persons.list_paginated` con `?lead_status_id=`).

### `repositories/channel_account.py`

```python
class ChannelAccountRepository(BaseRepository[ChannelAccount]):
    ALLOWED_FIELDS: set[str] = {
        "channel_type", "name", "external_identifier", "active",
        "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(ChannelAccount)

    async def get_by_external_id(
        self, db: AsyncSession, channel_type: str, external_identifier: str
    ) -> ChannelAccount | None:
        """Resuelve la cuenta viva por (channel_type, external_identifier). Respalda el
        guard de unicidad (409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN)."""
        result = await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.channel_type == channel_type,
                ChannelAccount.external_identifier == external_identifier,
                ChannelAccount.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[ChannelAccount]:
        result = await db.execute(
            select(ChannelAccount)
            .where(ChannelAccount.active.is_(True), ChannelAccount.deleted_at.is_(None))
            .order_by(ChannelAccount.name.asc())
        )
        return list(result.scalars().all())


channel_account_repository = ChannelAccountRepository()
```

> El webhook carga la cuenta por **id** (`get_by_id`, viene en la URL `/webhooks/whatsapp/{channel_account_id}`), no por external_id — `BaseRepository.get_by_id` ya filtra `deleted_at IS NULL`. Si la cuenta no existe / está soft-deleted → 404 sin procesar.

### `repositories/conversation.py` (denormalización batch sin N+1)

```python
class ConversationRepository(BaseRepository[Conversation]):
    # SOLO columnas reales de conversation (lección cd10c78). person.full_name, channel
    # name, assignee full_name, last_message_preview son DENORMALIZADOS → NOT here.
    # defaultSort = last_message_at desc (el prefetch del RSC y el defaultSort de la
    # tabla DEBEN coincidir — lección crm/staff).
    ALLOWED_FIELDS: set[str] = {
        "status", "assignee_type", "assignee_user_id", "channel_account_id",
        "last_message_at", "created_on", "unread_count",
    }

    def __init__(self) -> None:
        super().__init__(Conversation)

    async def get_open(
        self, db: AsyncSession, person_id: str, channel_account_id: str
    ) -> Conversation | None:
        """El hilo abierto de (person, channel) — el core de find_or_create_open."""
        result = await db.execute(
            select(Conversation).where(
                Conversation.person_id == person_id,
                Conversation.channel_account_id == channel_account_id,
                Conversation.status == ConversationStatus.open.value,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def has_other_open(
        self, db: AsyncSession, person_id: str, channel_account_id: str, exclude_id: str
    ) -> bool:
        """Guard de reopen (409 CONVERSATION_ALREADY_OPEN): ¿hay OTRA open para el mismo
        (person, channel) distinta de exclude_id?"""
        result = await db.execute(
            select(Conversation.id).where(
                Conversation.person_id == person_id,
                Conversation.channel_account_id == channel_account_id,
                Conversation.status == ConversationStatus.open.value,
                Conversation.deleted_at.is_(None),
                Conversation.id != exclude_id,
            )
        )
        return result.scalars().first() is not None

    async def list_inbox(
        self,
        db: AsyncSession,
        query_request: QueryRequest,
        *,
        channel_account_id: str | None = None,
        status: str | None = None,
        assignee_user_id: str | None = None,
        unassigned: bool | None = None,
    ) -> tuple[list[Conversation], int]:
        """Inbox global / mi bandeja. Los deep-links se aplican como filtros sobre
        columnas REALES antes de delegar el sort/paginado a get_paginated (que respeta
        ALLOWED_FIELDS). `unassigned=True` ⇒ assignee_type='unassigned'."""
        extra = []
        if channel_account_id is not None:
            extra.append(Conversation.channel_account_id == channel_account_id)
        if status is not None:
            extra.append(Conversation.status == status)
        if assignee_user_id is not None:
            extra.append(Conversation.assignee_user_id == assignee_user_id)
        if unassigned:
            extra.append(Conversation.assignee_type == AssigneeType.unassigned.value)
        return await self.get_paginated(db, query_request, extra_filters=extra)
```

> **`extra_filters`**: igual que `crm.persons.list_paginated_filtered` / `staff.list_active(branch_id=...)` — el repo arma una lista de cláusulas SQLAlchemy sobre columnas reales y se las pasa a `get_paginated` (que aplica `ALLOWED_FIELDS` para el sort/filtros dinámicos del body). `defaultSort = last_message_at desc`.

### `repositories/message.py`

```python
class MessageRepository(BaseRepository[Message]):
    ALLOWED_FIELDS: set[str] = {"direction", "sender_type", "content_type", "sent_at", "created_on"}

    def __init__(self) -> None:
        super().__init__(Message)

    async def get_by_external_id(
        self, db: AsyncSession, conversation_id: str, external_id: str
    ) -> Message | None:
        """Dedup de webhook (idempotencia). Respalda el UNIQUE parcial."""
        result = await db.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.external_id == external_id,
            )
        )
        return result.scalars().first()

    async def get_by_external_id_global(
        self, db: AsyncSession, external_id: str
    ) -> Message | None:
        """apply_status (statuses[]) trae solo el wamid, sin conversation_id → resolver
        global por external_id (raro colisionar; el wamid es único en Meta)."""
        result = await db.execute(select(Message).where(Message.external_id == external_id))
        return result.scalars().first()

    async def append(self, db: AsyncSession, message: Message) -> Message:
        db.add(message)
        await db.flush()
        return message

    async def list_for_conversation(
        self, db: AsyncSession, query_request: QueryRequest, *, conversation_id: str
    ) -> tuple[list[Message], int]:
        """Paginado del hilo (asc por sent_at; el front pinta cronológico). conversation_id
        como filtro real."""
        return await self.get_paginated(
            db, query_request, extra_filters=[Message.conversation_id == conversation_id]
        )


message_repository = MessageRepository()
```

### `repositories/message_attachment.py`

```python
class MessageAttachmentRepository(BaseRepository[MessageAttachment]):
    ALLOWED_FIELDS: set[str] = set()  # nunca filtrable directo; batch por message_id

    def __init__(self) -> None:
        super().__init__(MessageAttachment)

    async def attachments_map(
        self, db: AsyncSession, message_ids: list[str]
    ) -> dict[str, list[MessageAttachment]]:
        """Batch: message_id → [attachments] para una página de mensajes (sin N+1).
        En el MVP devuelve {} (texto primero); F4 lo puebla."""
        if not message_ids:
            return {}
        result = await db.execute(
            select(MessageAttachment).where(
                MessageAttachment.message_id.in_(message_ids),
                MessageAttachment.active.is_(True),
            )
        )
        out: dict[str, list[MessageAttachment]] = {}
        for att in result.scalars().all():
            out.setdefault(att.message_id, []).append(att)
        return out


message_attachment_repository = MessageAttachmentRepository()
```

### `repositories/conversation_assignment_log.py`

```python
class ConversationAssignmentLogRepository(BaseRepository[ConversationAssignmentLog]):
    ALLOWED_FIELDS: set[str] = set()  # consultado por conversation_id

    def __init__(self) -> None:
        super().__init__(ConversationAssignmentLog)

    async def get_current_open(
        self, db: AsyncSession, conversation_id: str
    ) -> ConversationAssignmentLog | None:
        """El log vigente (ended_at IS NULL) — a lo sumo uno (invariante de service)."""
        result = await db.execute(
            select(ConversationAssignmentLog).where(
                ConversationAssignmentLog.conversation_id == conversation_id,
                ConversationAssignmentLog.ended_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list_for_conversation(
        self, db: AsyncSession, conversation_id: str
    ) -> list[ConversationAssignmentLog]:
        """Historial de handoff (ConversationDetail.assignment_history), más reciente
        primero."""
        result = await db.execute(
            select(ConversationAssignmentLog)
            .where(ConversationAssignmentLog.conversation_id == conversation_id)
            .order_by(ConversationAssignmentLog.started_at.desc())
        )
        return list(result.scalars().all())


conversation_assignment_log_repository = ConversationAssignmentLogRepository()
```

> **Denormalización sin N+1** (patrón crm/staff): `conversation.list_inbox` hace `get_paginated` + batch maps por `IN (...)`:
> - **person**: recolectar `person_id` de la página → un batch lookup en crm. Se reusa `crm.person_repository` con un helper aditivo **mínimo** (ver §8 "no-cambios a crm"): se construye un `PersonOption` por persona. Si la complejidad lo amerita, conversations añade un batch `person_option_map(db, person_ids)` a `crm.person_repository` (aditivo, como `staff.branch_repository.get_by_ids`); decisión final en F2 (anotado en `deviations_or_gaps`).
> - **channel**: `channel_account` por id (batch o cache local; pocas cuentas).
> - **assignee**: `assignee_user_id` → `UserAuditInfo` vía `user_repository.get_audit_info_map`.
> - **audit**: `created_by`/`updated_by` → `get_audit_info_map` (mismo set).
> Cero N+1. `_to_list_item` recibe esos maps como kwargs (igual que `crm._to_item`). `MessageItem.attachments` se arma con `attachments_map` (batch por `message_id`). `ConversationDetail.assignment_history` con `list_for_conversation` + un `get_audit_info_map` sobre todos los `*_user_id` de los logs.

---

## 6. Services (módulos de funciones)

### `services/channel_account.py` — CRUD + `get_credentials`

CRUD estándar (molde `catalog.vertical`): `list_paginated`, `create` (guard unicidad), `get_by_id`, `update`, `soft_delete`, `list_active`. Más el helper **server-only** `get_credentials`:

```python
async def create(db, payload: ChannelAccountCreate, *, actor_id: str) -> SingleResponse[ChannelAccountDetail]:
    existing = await channel_account_repository.get_by_external_id(
        db, payload.channel_type.value, payload.external_identifier
    )
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe una cuenta de canal '{payload.channel_type.value}' con el identificador "
            f"'{payload.external_identifier}'",
            code="CHANNEL_ACCOUNT_EXTERNAL_TAKEN",
        )
    now = utc_now()
    ca = ChannelAccount(
        id=generate_uuid(), channel_type=payload.channel_type.value, name=payload.name,
        external_identifier=payload.external_identifier, secret_name=payload.secret_name,
        webhook_verify_token=payload.webhook_verify_token, phone_number_id=payload.phone_number_id,
        active=True, created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(ca); await db.flush()
    # reload + audit users → _to_detail (has_secret = secret_name is not None; jamás el valor)
    ...


async def get_credentials(db, ca: ChannelAccount) -> dict:
    """SERVER-ONLY. Resuelve las credenciales del canal para firmar/verificar/enviar.
    Si ca.secret_name está set → secrets.resolve(ca.secret_name) (Secret Manager, cacheado).
    Si NULL o estamos en dev/test (ENV_NAME=dev) → fallback a env (Settings.WHATSAPP_*).
    Empty/404 → CHANNEL_CREDENTIALS_MISSING. NUNCA se expone por la API."""
    from app.core import secrets
    settings = get_settings()
    if ca.secret_name and settings.ENV_NAME != "dev":
        creds = await secrets.resolve(ca.secret_name)
    else:
        creds = {
            "access_token": settings.WHATSAPP_ACCESS_TOKEN,
            "app_secret": settings.WHATSAPP_APP_SECRET,
            "phone_number_id": ca.phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID,
        }
    if not creds or not creds.get("access_token") or not creds.get("app_secret"):
        raise BadRequestException(
            "Faltan las credenciales del canal (Secret Manager / env)",
            code="CHANNEL_CREDENTIALS_MISSING",  # ver §9: el handler lo emite 500 o 400 según contexto
        )
    return creds
```

> **`CHANNEL_CREDENTIALS_MISSING`**: la spec §9 lo lista como **500** (es una mala config del operador, no del request). En el flujo de webhook (verificación de firma) se trata como 500/403 según donde falte; en el flujo outbound se persiste el mensaje fallido. Detalle en §9. `phone_number_id` se prefiere de la columna `ca.phone_number_id` (practicidad de la URL) y cae al env solo en fallback.

### `services/conversation.py` — `find_or_create_open` (auto-asignación) + handoff

```python
async def find_or_create_open(
    db, *, person: Person, channel_account: ChannelAccount, actor_id: str = SYSTEM_USER_ID
) -> Conversation:
    """Idempotente: devuelve el hilo abierto de (person, channel) si existe; si no, crea
    uno NUEVO con AUTO-ASIGNACIÓN al dueño del lead de la Person (continuidad
    'mis leads = mis chats') y fallback a 'unassigned' (bandeja compartida)."""
    open_conv = await conversation_repository.get_open(db, person.id, channel_account.id)
    if open_conv is not None:
        return open_conv
    now = utc_now()
    # AUTO-ASIGNACIÓN: leer el dueño del lead vía crm (lectura aditiva, sin cambio a crm).
    advisor_map = await lead_assignment_repository.advisor_map(db, [person.id])
    advisor_id = advisor_map.get(person.id)
    if advisor_id is not None:
        assignee_type, assignee_user_id = AssigneeType.advisor, advisor_id
    else:
        assignee_type, assignee_user_id = AssigneeType.unassigned, None
    conv = Conversation(
        id=generate_uuid(), channel_account_id=channel_account.id, person_id=person.id,
        status=ConversationStatus.open.value, assignee_type=assignee_type.value,
        assignee_user_id=assignee_user_id, opened_at=now, unread_count=0, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(conv); await db.flush()
    # Primer ConversationAssignmentLog (from=NULL → to=assignee; by_actor=NULL si auto).
    await _open_assignment_log(db, conv, from_type=None, from_user=None,
        to_type=assignee_type, to_user=assignee_user_id, by_actor=None, reason="Auto-asignación", now=now)
    await db.flush()
    return conv
```

> **Auto-asignación al dueño del lead (decisión §1.3 de la spec)**: usa `crm.lead_assignment_repository.advisor_map(db, [person_id])` (lectura existente, **sin cambio a crm**) para resolver el asesor activo de la Person; si hay → `assignee_type='advisor'`; si no → `unassigned`. El asesor puede reasignar/tomar igual. El primer `ConversationAssignmentLog` registra el estado inicial (`from_*=NULL`; `by_actor=NULL` = automático).

```python
async def take(db, conversation_id: str, *, actor_id: str, reason: str | None = None) -> SingleResponse[ConversationDetail]:
    conv = await _get_or_404(db, conversation_id)
    now = utc_now()
    # Cerrar el log vigente + abrir uno nuevo a advisor=actor (misma tx).
    await _reassign(db, conv, to_type=AssigneeType.advisor, to_user=actor_id, by_actor=actor_id, reason=reason, now=now)
    conv.assignee_type = AssigneeType.advisor.value
    conv.assignee_user_id = actor_id
    conv.unread_count = 0  # tomar = marcar leído
    conv.updated_by = actor_id; conv.updated_on = now
    # Emitir CONVERSATION_TAKEN a la timeline de crm (si la conversación tiene person).
    if conv.person_id is not None:
        await lead_activity.log(db, conv.person_id, ActivityType.CONVERSATION_TAKEN,
            advisor_user_id=actor_id, actor_id=actor_id, related_conversation_id=conv.id,
            payload={"channel_account_id": conv.channel_account_id})
    await db.flush()
    return await _reload_detail(db, conv)


async def release(db, conversation_id: str, payload: ReleaseConversationRequest, *, actor_id: str) -> SingleResponse[ConversationDetail]:
    conv = await _get_or_404(db, conversation_id)
    # to_assignee_type ∈ {bot, unassigned}; advisor → INVALID_ASSIGNEE (advisor = take).
    if payload.to_assignee_type == AssigneeType.advisor:
        raise BadRequestException("Para asignar a un asesor usar 'tomar'", code="INVALID_ASSIGNEE")
    if payload.to_assignee_type == AssigneeType.bot and payload.to_bot_configuration_id is None:
        # bots no existe en el MVP → en la práctica solo unassigned. Guard de invariante.
        raise BadRequestException("Falta la configuración de bot", code="INVALID_ASSIGNEE")
    now = utc_now()
    await _reassign(db, conv, to_type=payload.to_assignee_type, to_user=None,
        by_actor=actor_id, reason=payload.reason, now=now)
    conv.assignee_type = payload.to_assignee_type.value
    conv.assignee_user_id = None
    conv.updated_by = actor_id; conv.updated_on = now
    if conv.person_id is not None:
        await lead_activity.log(db, conv.person_id, ActivityType.CONVERSATION_RELEASED,
            advisor_user_id=actor_id, actor_id=actor_id, related_conversation_id=conv.id,
            payload={"to_assignee_type": payload.to_assignee_type.value})
    await db.flush()
    return await _reload_detail(db, conv)


async def close(db, conversation_id: str, *, actor_id: str) -> SingleResponse[ConversationDetail]:
    conv = await _get_or_404(db, conversation_id)
    if conv.status == ConversationStatus.closed.value:
        return await _reload_detail(db, conv)  # idempotente
    now = utc_now()
    conv.status = ConversationStatus.closed.value
    conv.closed_at = now
    conv.updated_by = actor_id; conv.updated_on = now
    await _close_current_log(db, conv.id, now)  # cierra el ConversationAssignmentLog vigente
    await db.flush()
    return await _reload_detail(db, conv)


async def reopen(db, conversation_id: str, *, actor_id: str) -> SingleResponse[ConversationDetail]:
    conv = await _get_or_404(db, conversation_id)
    # Guard: no puede haber OTRA open para (person, channel) → 409.
    if conv.person_id is not None and await conversation_repository.has_other_open(
        db, conv.person_id, conv.channel_account_id, conv.id
    ):
        raise ConflictException("Ya hay una conversación abierta para este contacto en este canal",
                                code="CONVERSATION_ALREADY_OPEN")
    now = utc_now()
    conv.status = ConversationStatus.open.value
    conv.closed_at = None
    conv.updated_by = actor_id; conv.updated_on = now
    # Reabrir un nuevo log vigente con el assignee actual (no resetea la asignación).
    await _open_assignment_log(db, conv, from_type=None, from_user=None,
        to_type=AssigneeType(conv.assignee_type), to_user=conv.assignee_user_id,
        by_actor=actor_id, reason="Reapertura", now=now)
    await db.flush()
    return await _reload_detail(db, conv)


async def mark_read(db, conversation_id: str, *, actor_id: str) -> SingleResponse[ConversationDetail]:
    conv = await _get_or_404(db, conversation_id)
    conv.unread_count = 0
    conv.updated_by = actor_id; conv.updated_on = utc_now()
    await db.flush()
    return await _reload_detail(db, conv)
```

> **`_reassign` / `_open_assignment_log` / `_close_current_log`** son helpers privados que materializan el invariante "una sola fila vigente": `_close_current_log` hace `UPDATE ... SET ended_at=now WHERE conversation_id=? AND ended_at IS NULL`; `_open_assignment_log` inserta la nueva fila vigente; `_reassign` = `_close_current_log` + `_open_assignment_log` con el `from_*` tomado del estado actual de la conversación. Todo en la tx del request.
> **Emisión a la timeline de crm (decisión §1)**: SOLO `CONVERSATION_TAKEN` (take) y `CONVERSATION_RELEASED` (release), vía `crm.lead_activity.log(..., related_conversation_id=conv.id)`. **NO** `MESSAGE_SENT` por-mensaje (evita inundar el timeline lead-céntrico y la escritura cross-módulo en el hot path del envío). Estos eventos NO son de `crm.ADVISOR_ACTIVITY_TYPES` → `crm._get_editable_owned` los rechaza con 404 → **audit trail inmutable** (el asesor no los puede editar/borrar). Solo se emiten si `conv.person_id is not None`.

### `services/message.py` — `persist_inbound`, `send_outbound` (Meta Graph API), `apply_status`

```python
async def persist_inbound(
    db, *, conversation: Conversation, external_id: str | None, content: str | None,
    content_type: ContentType, sent_at: datetime, provider_payload: dict,
) -> Message | None:
    """Persiste un mensaje entrante. DEDUP por external_id (idempotencia del webhook de
    Meta): si ya existe en la conversación → no-op (devuelve None). Incrementa unread_count
    y actualiza last_message_at/preview. NO toca crm (no emite MESSAGE_SENT — §1)."""
    if external_id is not None:
        dup = await message_repository.get_by_external_id(db, conversation.id, external_id)
        if dup is not None:
            return None  # ya procesado (reenvío de Meta)
    now = utc_now()
    msg = Message(
        id=generate_uuid(), conversation_id=conversation.id,
        direction=MessageDirection.inbound.value, sender_type=SenderType.contact.value,
        sender_user_id=None, content_type=content_type.value, content=content,
        external_id=external_id, external_status=None, sent_at=sent_at, provider_payload=provider_payload,
        active=True, created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    await message_repository.append(db, msg)
    conversation.unread_count += 1
    conversation.last_message_at = sent_at
    conversation.last_message_preview = (content or "")[:255]
    conversation.updated_by = SYSTEM_USER_ID; conversation.updated_on = now
    return msg


async def send_outbound(
    db, conversation_id: str, payload: MessageSendRequest, *, actor_id: str
) -> SingleResponse[MessageItem]:
    conv = await conversation_repository.get_by_id(db, conversation_id)
    if conv is None:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
    if conv.status != ConversationStatus.open.value:
        raise BadRequestException("La conversación está cerrada", code="CONVERSATION_NOT_OPEN")
    # Autorización: actor debe ser el assignee advisor.
    if conv.assignee_type != AssigneeType.advisor.value or conv.assignee_user_id != actor_id:
        raise ForbiddenException("No sos el asesor asignado a esta conversación",
                                 code="NOT_CONVERSATION_ASSIGNEE")
    if payload.content_type != ContentType.text:
        raise BadRequestException("Solo se admite texto en esta versión", code="UNSUPPORTED_CONTENT_TYPE")
    now = utc_now()
    # 1) Persistir el Message PRIMERO (external_status=NULL) — el envío puede fallar.
    msg = Message(
        id=generate_uuid(), conversation_id=conv.id, direction=MessageDirection.outbound.value,
        sender_type=SenderType.advisor.value, sender_user_id=actor_id,
        content_type=ContentType.text.value, content=payload.content, external_id=None,
        external_status=None, sent_at=now, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    await message_repository.append(db, msg)
    # 2) Enviar REAL contra Meta Graph API. Falla → persistir el message como fallido (200).
    ca = await channel_account_repository.get_by_id(db, conv.channel_account_id)
    try:
        creds = await channel_account_service.get_credentials(db, ca)
        result = await _meta_send_text(creds, to=<person primary identifier>, body=payload.content)
        msg.external_id = result["wamid"]
        msg.external_status = MessageExternalStatus.sent.value
    except Exception as exc:  # red / 4xx-5xx de Meta / credenciales
        msg.failed_at = now
        msg.failure_reason = str(exc)[:255]
        msg.external_status = MessageExternalStatus.failed.value
        logger.warning("outbound send failed", extra={"conversation_id": conv.id, "error": str(exc)})
    # 3) Actualizar denormalizados de la conversación (aun si falló — el intento cuenta).
    conv.last_message_at = now
    conv.last_message_preview = payload.content[:255]
    conv.updated_by = actor_id; conv.updated_on = now
    await db.flush()
    return SingleResponse(data=await _reload_message_item(db, msg))  # 200 incluso si failed


async def apply_status(db, *, external_id: str, status: str, ts: datetime) -> None:
    """statuses[] del webhook → marca delivered_at/read_at/failed_at + external_status.
    No-op si el mensaje no existe (status de un mensaje que no enviamos)."""
    msg = await message_repository.get_by_external_id_global(db, external_id)
    if msg is None:
        return
    if status == "delivered": msg.delivered_at = ts
    elif status == "read":    msg.read_at = ts
    elif status == "failed":  msg.failed_at = ts
    msg.external_status = status
    msg.updated_on = utc_now()
```

> **Outbound fallido (decisión §1)**: el `Message` se persiste **siempre** (marcado `failed_at`/`failure_reason`/`external_status='failed'`); el endpoint devuelve **200** con el mensaje en estado fallido (la UI muestra "Falló el envío / Reintentar"), **NO** 502. Esto evita perder el texto que el asesor escribió y hace el reintento trivial (re-`POST` con el mismo content). `MESSAGE_SEND_FAILED` se usa solo internamente (log/payload), no como status HTTP.
> **`_meta_send_text`** (en `services/message.py` o un thin client `services/webhook_processor/whatsapp.py`): `POST https://graph.facebook.com/v<ver>/{phone_number_id}/messages` con `Authorization: Bearer {access_token}` y body `{messaging_product:"whatsapp", to, type:"text", text:{body}}`. Usa `httpx.AsyncClient` (ya en deps del template para tests; si no, agregar). El `to` es el identifier primario WhatsApp de la Person (resuelto vía `conversation.person_id` → identifier). Timeout corto (≈10 s).

### `services/webhook_processor/whatsapp.py` — verify firma + parse + orquestación

```python
import hashlib
import hmac

from app.modules.crm.enums import ChannelType
from app.modules.crm.schemas.person import PersonContactIdentifierInput, PersonCreate
from app.modules.crm.services import person as crm_person


def verify_signature(*, raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC_SHA256(app_secret, raw_body). Comparación
    en tiempo constante (hmac.compare_digest). El raw_body es el cuerpo SIN re-serializar
    (Meta firma los bytes exactos)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + expected, signature_header)


async def process_inbound(db, *, payload: dict, channel_account: ChannelAccount) -> None:
    """Parse del payload de WhatsApp Cloud API: entry[].changes[].value.{messages[], statuses[],
    contacts[]}. Flujo SÍNCRONO (MVP, sin bot lento). Texto primero (media diferida F4)."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {c["wa_id"]: c for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                wa_id = m["from"]
                pushname = (contacts.get(wa_id, {}).get("profile", {}).get("name") or "").strip()
                # 1) Resolver/crear la Person vía crm (hardened con advisory lock — §8).
                person = await crm_person.find_by_identifier_or_create(
                    db, ChannelType.whatsapp, wa_id,
                    profile=PersonCreate(
                        first_name=(pushname[:80] or "Contacto"),
                        last_name="(WhatsApp)",         # placeholder editable; last_name exige min_length=1
                        identifiers=[],                  # find_or_create construye el suyo → lista vacía
                    ),
                    campaign_id=channel_account.default_campaign_id,
                )
                # 2) Hilo abierto (auto-asignación al dueño del lead / unassigned).
                conv = await conversation_service.find_or_create_open(
                    db, person=person, channel_account=channel_account)
                # 3) Texto primero: solo type='text' se persiste con content; otros tipos
                #    se persisten como content_type correspondiente SIN media (F4 cablea download).
                content, content_type = _extract_text(m)  # ("hola", ContentType.text) | (None, ContentType.image)
                await message_service.persist_inbound(
                    db, conversation=conv, external_id=m.get("id"), content=content,
                    content_type=content_type, sent_at=_ts(m.get("timestamp")), provider_payload=m)
            for s in value.get("statuses", []):
                await message_service.apply_status(
                    db, external_id=s["id"], status=s["status"], ts=_ts(s.get("timestamp")))
```

> **Contacto desconocido (default §1)**: `PersonCreate(first_name = pushname.trim()[:80] o "Contacto", last_name = "(WhatsApp)", identifiers=[])`. `last_name` exige `min_length=1` (validador de `crm.PersonCreate`); el placeholder `"(WhatsApp)"` es editable por el asesor. `find_by_identifier_or_create` **ignora** `profile.identifiers` (construye el suyo con `(whatsapp, wa_id)` primario no verificado) → se pasa lista vacía.
> **Flujo síncrono del MVP**: todo (verify firma + dedup + resolver Person + persistir + status) ocurre **antes** del 200, sin `BackgroundTasks` (rápido; no hay bot que genere auto-reply lento). **Cuándo migrar a cola/async**: cuando `bots` (#6) agregue auto-reply lento (LLM) → 200 inmediato + `BackgroundTasks` (patrón webhook async, ver feedback de memoria) o cola (Pub/Sub) + Cloud Run `--no-cpu-throttling --min-instances 1`. Anotado para `bots`.

---

## 7. `app/core/secrets.py` — secret_resolver (Secret Manager SDK + cache TTL) — ADR-010

```python
"""
Per-account secret resolution via GCP Secret Manager SDK at RUNTIME (ADR-010). The
template injects FIXED secrets per env via Cloud Run --set-secrets (SECRET_KEY, DB
creds become env vars read by Settings). Per-ChannelAccount credentials need DYNAMIC
resolution to support N WhatsApp numbers without redeploy → this resolver.

- resolve(secret_name) -> dict: parses the secret payload as JSON
  {access_token, app_secret, phone_number_id?}, with an in-memory TTL cache (~10 min)
  so we don't hit Secret Manager per webhook.
- The SDK client is LAZY-initialised (not at import) so the app boots without GCP
  (local/test). The smoke (sqlite) NEVER calls Secret Manager (channel_account.get_credentials
  takes the env fallback when ENV_NAME=dev / secret_name is NULL).
- Cloud Run SA already has roles/secretmanager.secretAccessor.
"""

from __future__ import annotations

import json
import time

from app.core.config import get_settings
from app.core.exceptions import BadRequestException

_CACHE: dict[str, tuple[dict, float]] = {}   # secret_name -> (creds, expires_at_monotonic)
_TTL_SECONDS = 600
_client = None  # lazy


def _get_client():
    global _client
    if _client is None:
        # Import diferido: el paquete solo se necesita en Cloud Run; el boot local no lo carga.
        from google.cloud import secretmanager
        _client = secretmanager.SecretManagerServiceAsyncClient()
    return _client


async def resolve(secret_name: str) -> dict:
    """secret_name puede ser el nombre corto (medisage-whatsapp-estetica-qa) o el resource
    name completo (projects/.../secrets/.../versions/latest). Cachea por TTL."""
    now = time.monotonic()
    cached = _CACHE.get(secret_name)
    if cached is not None and cached[1] > now:
        return cached[0]
    settings = get_settings()
    resource = (
        secret_name
        if secret_name.startswith("projects/")
        else f"projects/{settings.GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
    )
    try:
        client = _get_client()
        response = await client.access_secret_version(name=resource)
        creds = json.loads(response.payload.data.decode("utf-8"))
    except Exception as exc:  # NotFound / PermissionDenied / JSON inválido
        raise BadRequestException(
            "No se pudo resolver el secreto del canal", code="CHANNEL_CREDENTIALS_MISSING"
        ) from exc
    _CACHE[secret_name] = (creds, now + _TTL_SECONDS)
    return creds
```

> **Dependencia nueva**: `google-cloud-secret-manager` (pin en `pyproject.toml`, ej. `google-cloud-secret-manager>=2.20,<3`). **Settings nuevos** (en `app/core/config.py:Settings`, defaults vacíos): `GCP_PROJECT_ID: str = ""`, `WHATSAPP_ACCESS_TOKEN: str = ""`, `WHATSAPP_APP_SECRET: str = ""`, `WHATSAPP_PHONE_NUMBER_ID: str = ""`. El smoke (sqlite, `ENV_NAME=dev`) toma el fallback env y NUNCA llama Secret Manager. **Cloud Run**: crear los secretos (`medisage-whatsapp-*-{qa,prod}` con payload JSON `{access_token, app_secret, phone_number_id}`) al desplegar F1/F2; la SA ya tiene `secretAccessor`. El cliente se inicializa lazy (no rompe el boot sin GCP). Reusable por `bots` si necesita secretos por-tenant.

---

## 8. Cambios aditivos a crm (detallados)

> Todos backward-compatible (los callers existentes de crm no cambian de comportamiento). Viven DENTRO de crm (la función dueña), benefician a cualquier caller.

### 8.1 Advisory lock en `find_by_identifier_or_create` (hardening de concurrencia) — CAMBIO #1

`find_by_identifier_or_create` hoy hace get-then-insert SIN lock (sin callers en prod hasta ahora). Bajo webhooks concurrentes para el MISMO número nuevo, dos requests insertan → `IntegrityError` (el UNIQUE parcial `(channel_type, identifier)` lo respalda, pero la tx perdedora aborta feo). Fix: **advisory lock transaccional Postgres** al inicio, keyed por `(channel_type, identifier)`:

```python
# crm/services/person.py — primera línea de find_by_identifier_or_create
from sqlalchemy import func, select

if db.bind.dialect.name == "postgresql":
    await db.execute(
        select(func.pg_advisory_xact_lock(
            func.hashtextextended(f"{channel_type.value}:{identifier}", 0)
        ))
    )
# sqlite: no-op (el smoke es single-thread).
```

Serializa el get-then-insert por identifier (el segundo request espera al commit del primero, hace el `get_by_identifier` y devuelve la Person ya creada — idempotente). **Alternativa documentada (no elegida)**: try/except `IntegrityError` → rollback parcial → re-get; descartada por la fricción con la sesión-por-request (un rollback parcial aborta la tx entera). El lock se libera al commit/rollback de la tx (`_xact_`).

### 8.2 Parámetro `related_conversation_id` en `lead_activity.log` — CAMBIO #2

Firma actual (verificada): `log(db, person_id, activity_type, *, advisor_user_id, actor_id, content=None, scheduled_for=None, completed_at=None, outcome=None, payload=None) -> LeadActivity`. Agregar parámetro opcional al final y setearlo en el modelo:

```python
async def log(
    db, person_id, activity_type, *, advisor_user_id, actor_id,
    content=None, scheduled_for=None, completed_at=None, outcome=None, payload=None,
    related_conversation_id: str | None = None,   # ← NUEVO (backward-compatible)
) -> LeadActivity:
    ...
    activity = LeadActivity(
        ..., related_conversation_id=related_conversation_id,   # ← NUEVO
    )
```

La columna `lead_activity.related_conversation_id` ya existe (`varchar(36)`+index, sin constraint, ADR-009). conversations la pasa al emitir `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED`. Los callers existentes (`STATUS_CHANGE`/`REASSIGNED`/`CAMPAIGN_ATTRIBUTION`/composer del asesor) no lo pasan → siguen NULL. **No** se agrega validación de tipo aquí; conversations solo emite tipos que NO están en `crm.ADVISOR_ACTIVITY_TYPES`, así que `crm._get_editable_owned` ya los hace inmutables (404 al editar/borrar) — audit trail. ✔

### 8.3 FK aditiva `lead_activity.related_conversation_id → conversation.id` — CAMBIO #3 (en la migración 0016, Postgres-only)

conversations agrega la **constraint aditiva** en su migración de threads (`0016`), Postgres-only:

```python
op.create_foreign_key(
    "fk_lead_activity_conversation", "lead_activity", "conversation",
    ["related_conversation_id"], ["id"],
)
```

Seguro (todos los valores actuales de la columna son NULL). **NO** se agrega `relationship` ORM (mantiene el modelo crm intacto, consistente con el patrón "sin relationship cross-módulo"). **Caveat sqlite**: el `ALTER ADD FK` no corre en sqlite/create_all (la migración solo corre en Postgres; el smoke usa create_all sobre los modelos, donde la columna sigue siendo un `String(36)` plano). Por eso el FK se valida vía QA E2E sobre Postgres, no en el smoke.

### 8.4 Lectura del dueño del lead (auto-asignación) — SIN cambio a crm

conversations usa el repo existente `crm.lead_assignment_repository.advisor_map(db, [person_id])` (devuelve `{person_id: advisor_user_id}` de la asignación viva) para resolver el asesor activo de la Person al crear la conversación. Lectura aditiva, **sin cambio a crm**. (Verificado en `crm/repositories/lead_assignment.py`.)

---

## 9. Routers + Webhooks (top-level)

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; `actor: CurrentAuth` aparte cuando se necesita el id para audit; `/active` antes de `/{id}`.

### 9.1 Endpoints autenticados — `/api/v1/conversations/`

| Método | Ruta | Permiso | Envelope / Body |
|---|---|---|---|
| POST | `/channel-accounts/list` | `CHANNEL_ACCOUNTS_READ` | `QueryRequest` → `PaginatedResponse[ChannelAccountItem]` |
| POST | `/channel-accounts` | `CHANNEL_ACCOUNTS_CREATE` | `ChannelAccountCreate` → `201 SingleResponse[ChannelAccountDetail]` |
| GET | `/channel-accounts/active` | `CHANNEL_ACCOUNTS_READ` | lista cruda `list[ChannelAccountOption]` |
| GET | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_READ` | `SingleResponse[ChannelAccountDetail]` |
| PUT | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_UPDATE` | `ChannelAccountUpdate` → `SingleResponse[ChannelAccountDetail]` |
| DELETE | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_DELETE` | `204` (soft-delete) |
| POST | `/list` | `CONVERSATIONS_READ` | inbox global. `QueryRequest` + query params deep-link → `PaginatedResponse[ConversationListItem]` |
| GET | `/{id}` | `CONVERSATIONS_READ` | `SingleResponse[ConversationDetail]` (+ `assignment_history`) |
| POST | `/{id}/messages/list` | `MESSAGES_READ` | `QueryRequest` → `PaginatedResponse[MessageItem]` (attachments inline) |
| POST | `/{id}/messages` | `MESSAGES_SEND` | `MessageSendRequest` → `SingleResponse[MessageItem]` (envío real; 200 aun si falló) |
| POST | `/{id}/take` | `CONVERSATIONS_TAKE` | `TakeConversationRequest` → `SingleResponse[ConversationDetail]` |
| POST | `/{id}/release` | `CONVERSATIONS_RELEASE` | `ReleaseConversationRequest` → `SingleResponse[ConversationDetail]` |
| POST | `/{id}/close` | `CONVERSATIONS_CLOSE` | `SingleResponse[ConversationDetail]` |
| POST | `/{id}/reopen` | `CONVERSATIONS_TAKE` | `SingleResponse[ConversationDetail]` (valida no-otra-open) |
| POST | `/{id}/mark-read` | `CONVERSATIONS_READ` | `SingleResponse[ConversationDetail]` |
| POST | `/me/conversations/list` | `MY_CONVERSATIONS_READ` | mi bandeja (`assignee_user_id = actor`). `QueryRequest` → `PaginatedResponse[ConversationListItem]` |

**Deep-links del inbox** (`POST /list`, como query params): `?channel_account_id=` / `?status=` / `?assignee_user_id=` / `?unassigned=true`. Traducidos a filtros sobre columnas reales en `conversation_repository.list_inbox` (NO van en `conditions` del body). **Búsqueda por nombre/identificador** = client-side sobre las filas denormalizadas (no son columnas de `conversation`). `defaultSort = last_message_at desc`.

```python
# routers/conversation.py (extracto)
router = APIRouter(prefix="/conversations", tags=["conversations"])  # NB: el aggregator ya pone /conversations → este sub-router NO repite el prefix; usa "" + las sub-rutas. (Ver nota.)

@router.post("/list", response_model=PaginatedResponse[ConversationListItem],
             dependencies=[Depends(RequirePermission("CONVERSATIONS_READ"))])
async def list_conversations(
    query: QueryRequest, db: DBSession,
    channel_account_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    assignee_user_id: Annotated[str | None, Query()] = None,
    unassigned: Annotated[bool | None, Query()] = None,
) -> PaginatedResponse[ConversationListItem]:
    return await conversation_service.list_inbox(
        db, query, channel_account_id=channel_account_id, status=status,
        assignee_user_id=assignee_user_id, unassigned=unassigned)

@router.post("/{conversation_id}/messages", response_model=SingleResponse[MessageItem],
             dependencies=[Depends(RequirePermission("MESSAGES_SEND"))])
async def send_message(conversation_id: ConvIdPath, payload: MessageSendRequest,
                       db: DBSession, actor: CurrentAuth) -> SingleResponse[MessageItem]:
    return await message_service.send_outbound(db, conversation_id, payload, actor_id=actor.id)

@router.post("/{conversation_id}/take", response_model=SingleResponse[ConversationDetail],
             dependencies=[Depends(RequirePermission("CONVERSATIONS_TAKE"))])
async def take_conversation(conversation_id: ConvIdPath, payload: TakeConversationRequest,
                            db: DBSession, actor: CurrentAuth) -> SingleResponse[ConversationDetail]:
    return await conversation_service.take(db, conversation_id, actor_id=actor.id, reason=payload.reason)
```

> **Nota de prefijos**: el aggregator `routers/__init__.py` declara `prefix="/conversations"`. Para evitar `/conversations/conversations`, los sub-routers `channel_account_router`/`conversation_router` usan prefijos relativos (`/channel-accounts`, y `""` para las rutas raíz como `/list`, `/{id}`). Es exactamente el mismo encaje que crm (`crm/routers/__init__.py` con `prefix="/crm"` + `person_router` con `prefix="/persons"`). Verificar al implementar que `POST /api/v1/conversations/list` resuelve (no `/conversations/conversations/list`).

### 9.2 Webhooks top-level — `app/routers/webhooks.py` (sin JWT)

| Método | Ruta | Auth | Propósito |
|---|---|---|---|
| GET | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT; compara `hub.verify_token` con `ChannelAccount.webhook_verify_token` | Meta verification challenge → devuelve `hub.challenge` (200, **text/plain**) o 403 |
| POST | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT; valida `X-Hub-Signature-256` (HMAC SHA256 del **body raw** con `app_secret`) | inbound messages + status callbacks → 200 |

```python
# app/routers/webhooks.py
from fastapi import APIRouter, Query, Request, Response, status

from app.core.dependencies import DBSession
from app.core.exceptions import ForbiddenException, NotFoundException
from app.modules.conversations.repositories.channel_account import channel_account_repository
from app.modules.conversations.services import channel_account as channel_account_service
from app.modules.conversations.services.webhook_processor import whatsapp as wa

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp/{channel_account_id}")
async def verify_whatsapp(
    channel_account_id: str, db: DBSession,
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")
    if hub_mode != "subscribe" or hub_verify_token != (ca.webhook_verify_token or ""):
        raise ForbiddenException("Token de verificación inválido", code="WEBHOOK_SIGNATURE_INVALID")
    return Response(content=hub_challenge, media_type="text/plain")  # Meta espera el challenge crudo


@router.post("/whatsapp/{channel_account_id}", status_code=status.HTTP_200_OK)
async def inbound_whatsapp(channel_account_id: str, request: Request, db: DBSession) -> dict:
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None or not ca.active:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")
    raw = await request.body()                         # bytes EXACTOS (Meta firma estos)
    creds = await channel_account_service.get_credentials(db, ca)
    if not wa.verify_signature(
        raw_body=raw, signature_header=request.headers.get("X-Hub-Signature-256"),
        app_secret=creds["app_secret"],
    ):
        raise ForbiddenException("Firma del webhook inválida", code="WEBHOOK_SIGNATURE_INVALID")
    payload = json.loads(raw)
    await wa.process_inbound(db, payload=payload, channel_account=ca)
    return {"success": True}                           # 200 tras procesar (síncrono)
```

> **Sin JWT**: el router top-level no usa `RequirePermission`/`CurrentAuth` — la autenticación es la firma HMAC (POST) / el verify token (GET), no el RBAC del template. **`raw_body`**: la firma de Meta es sobre los bytes exactos del body → `await request.body()` ANTES de parsear JSON (re-serializar cambiaría los bytes y rompería la firma). **404 antes de firma**: si la cuenta no existe/está inactiva → 404 sin tocar credenciales. **Error inesperado en `process_inbound`** → 500 (Meta reintenta; la idempotencia por `external_id` evita duplicados). **GET verify** devuelve el `hub.challenge` crudo (text/plain), NO un envelope. `telegram` diferido (URL futura `/webhooks/telegram/{channel_account_id}` con `X-Telegram-Bot-Api-Secret-Token`).

---

## 10. Códigos de error (detalle ES + code EN + HTTP)

| code (EN) | HTTP | detail (ES) | Dónde |
|---|---|---|---|
| `CHANNEL_ACCOUNT_NOT_FOUND` | 404 | "Cuenta de canal no encontrada" | channel_account get/update/delete; webhook router |
| `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` | 409 | "Ya existe una cuenta de canal '{type}' con el identificador '{ext}'" | channel_account.create/update (guard unicidad) |
| `CHANNEL_CREDENTIALS_MISSING` | 500 | "Faltan las credenciales del canal (Secret Manager / env)" | `get_credentials` / `secrets.resolve` (mala config del operador; 500. En outbound NO se levanta — el mensaje se persiste fallido) |
| `CONVERSATION_NOT_FOUND` | 404 | "Conversación no encontrada" | conversation get/take/release/close/reopen/mark-read; message send/list |
| `CONVERSATION_NOT_OPEN` | 400 | "La conversación está cerrada" | `send_outbound` (status != open) |
| `CONVERSATION_ALREADY_OPEN` | 409 | "Ya hay una conversación abierta para este contacto en este canal" | `reopen` (otra open para el mismo person+channel) |
| `INVALID_ASSIGNEE` | 400 | "Asignación inválida para el tipo indicado" | invariantes assignee_type↔assignee_user_id; `release` con advisor / bot sin config |
| `NOT_CONVERSATION_ASSIGNEE` | 403 | "No sos el asesor asignado a esta conversación" | `send_outbound` (actor ≠ assignee advisor) |
| `MESSAGE_NOT_FOUND` | 404 | "Mensaje no encontrado" | (reservado; lookups de mensaje puntuales) |
| `UNSUPPORTED_CONTENT_TYPE` | 400 | "Solo se admite texto en esta versión" | `send_outbound` (content_type ≠ text); MVP |
| `MESSAGE_SEND_FAILED` | — | (interno; log/payload) | `send_outbound`: el endpoint devuelve **200** con el message fallido, NO 502 |
| `WEBHOOK_SIGNATURE_INVALID` | 403 | "Firma del webhook inválida" / "Token de verificación inválido" | router top-level (POST firma / GET verify) |

> Excepciones de dominio del template (`app/core/exceptions.py`): `NotFoundException`(404), `AlreadyExistsException`(409), `BadRequestException`(400), `ForbiddenException`(403), `ConflictException`(409). El handler global traduce al envelope `{success:false, detail, code?, errors?}`. Los validators Pydantic (ej. `MessageSendRequest._text_only_mvp`, `min_length`) caen al 422 con `errors[]` y mensajes en inglés.

---

## 11. Permisos y roles (12 perms — F0 los agrega a seed)

Canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md) (`module="CONVERSATIONS"`). **NO redefinir** — solo agregarlos a `SEED_PERMISSIONS` si aún no están:

`MENU-CONVERSATIONS` · `CHANNEL_ACCOUNTS_READ` · `CHANNEL_ACCOUNTS_CREATE` · `CHANNEL_ACCOUNTS_UPDATE` · `CHANNEL_ACCOUNTS_DELETE` · `CONVERSATIONS_READ` · `CONVERSATIONS_TAKE` · `CONVERSATIONS_RELEASE` · `CONVERSATIONS_CLOSE` · `MESSAGES_READ` · `MESSAGES_SEND` · `MY_CONVERSATIONS_READ`.

- **ADMIN**: todos.
- **ASESOR**: `MENU-CONVERSATIONS`, `CONVERSATIONS_{READ,TAKE,RELEASE,CLOSE}`, `MESSAGES_{READ,SEND}`, `MY_CONVERSATIONS_READ` (**NO** `CHANNEL_ACCOUNTS_*` — solo admin configura canales).
- **DOCTOR**: sin permisos en conversations.

> Los sets `ASESOR_PERMISSION_CODES` / `ADMIN_PERMISSION_CODES` ya traen los códigos conversations en su forma canónica → el helper `_seed_role` los filtra por código (idempotente, a prueba de orden de módulos: se auto-expanden al existir el permiso). El user/role `SYSTEM` (`00000000-0000-0000-0000-000000000002`) ya existe (introducido en crm F0); `find_or_create_open`/`persist_inbound` lo usan como `created_by`/`actor_id` de las altas automáticas.

---

## 12. Plan de migraciones 0015 / 0016 (revid ≤ 32 chars; down_revision encadenado)

Migraciones **manuales y numeradas**. La última aplicada es `0014_crm_customer_lifecycle`; `conversations` encadena desde ahí. UNIQUE parciales con `WHERE ...` (Postgres) — el smoke no las corre (usa `create_all` sobre los modelos, donde el `sqlite_where` reproduce el índice). JSONB en las columnas `provider_payload`/`metadata`. **El smoke `create_all` NO corre la migración** (JSONB / ALTER ADD FK son Postgres-only) → la migración se valida vía QA E2E sobre Postgres (reuse del patrón crm `0013`).

### `0015_conv_channel_account.py` (F1 — channel_account) · revid `0015_conv_channel_account` (25 chars ✓)

```python
revision = "0015_conv_channel_account"
down_revision = "0014_crm_customer_lifecycle"

def upgrade() -> None:
    op.create_table(
        "channel_account",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("external_identifier", sa.String(length=255), nullable=False),
        sa.Column("secret_name", sa.String(length=255), nullable=True),
        sa.Column("webhook_verify_token", sa.String(length=255), nullable=True),
        sa.Column("phone_number_id", sa.String(length=64), nullable=True),
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=True),   # forward (ADR-009)
        sa.Column("default_campaign_id", sa.String(length=36), nullable=True),    # forward (ADR-009)
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_channel_account_type_external", "channel_account",
        ["channel_type", "external_identifier"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("ix_channel_account_bot_configuration_id", "channel_account", ["bot_configuration_id"])
    op.create_index("ix_channel_account_default_campaign_id", "channel_account", ["default_campaign_id"])

def downgrade() -> None:
    op.drop_index("ix_channel_account_default_campaign_id", table_name="channel_account")
    op.drop_index("ix_channel_account_bot_configuration_id", table_name="channel_account")
    op.drop_index("uq_channel_account_type_external", table_name="channel_account")
    op.drop_table("channel_account")
```

### `0016_conv_threads.py` (F2 — conversation + message + message_attachment + conversation_assignment_log + FK aditiva) · revid `0016_conv_threads` (17 chars ✓)

```python
revision = "0016_conv_threads"
down_revision = "0015_conv_channel_account"
from sqlalchemy.dialects import postgresql  # JSONB

def upgrade() -> None:
    # ── conversation (PK·A·SD·T) — UNIQUE PARCIAL 1-open ──────────────────
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_account_id", sa.String(length=36),
                  sa.ForeignKey("channel_account.id"), nullable=False),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_type", sa.String(length=20), nullable=False),
        sa.Column("assignee_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=True),   # forward (ADR-009)
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=255), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_conversation_channel_account_id", "conversation", ["channel_account_id"])
    op.create_index("ix_conversation_person_id", "conversation", ["person_id"])
    op.create_index("ix_conversation_assignee_user_id", "conversation", ["assignee_user_id"])
    op.create_index("ix_conversation_bot_configuration_id", "conversation", ["bot_configuration_id"])
    op.create_index("uq_conversation_person_channel_open", "conversation",
        ["person_id", "channel_account_id"], unique=True,
        postgresql_where=sa.text("status = 'open' AND deleted_at IS NULL"))

    # ── message (PK·A·T, SIN deleted_at — audit inmutable) ────────────────
    op.create_table(
        "message",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=True),   # forward (ADR-009)
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_status", sa.String(length=40), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("provider_payload", postgresql.JSONB(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])
    op.create_index("ix_message_conversation_external", "message",
        ["conversation_id", "external_id"], unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"))

    # ── message_attachment (PK·A·T, SIN deleted_at) — modelado, processing F4 ─
    op.create_table(
        "message_attachment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), sa.ForeignKey("message.id"), nullable=False),
        sa.Column("attachment_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("address_label", sa.String(length=255), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("external_media_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_message_attachment_message_id", "message_attachment", ["message_id"])

    # ── conversation_assignment_log (PK·A·T, SIN deleted_at — audit inmutable) ─
    op.create_table(
        "conversation_assignment_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("from_assignee_type", sa.String(length=20), nullable=True),
        sa.Column("from_assignee_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("to_assignee_type", sa.String(length=20), nullable=False),
        sa.Column("to_assignee_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("by_actor_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_conversation_assignment_log_conversation_id",
        "conversation_assignment_log", ["conversation_id"])

    # ── FK ADITIVA crm (ADR-009): lead_activity.related_conversation_id → conversation.id ─
    # Seguro: todos los valores actuales son NULL. Postgres-only (no corre en sqlite/create_all).
    op.create_foreign_key("fk_lead_activity_conversation", "lead_activity", "conversation",
        ["related_conversation_id"], ["id"])

def downgrade() -> None:
    op.drop_constraint("fk_lead_activity_conversation", "lead_activity", type_="foreignkey")
    op.drop_index("ix_conversation_assignment_log_conversation_id", table_name="conversation_assignment_log")
    op.drop_table("conversation_assignment_log")
    op.drop_index("ix_message_attachment_message_id", table_name="message_attachment")
    op.drop_table("message_attachment")
    op.drop_index("ix_message_conversation_external", table_name="message")
    op.drop_index("ix_message_conversation_id", table_name="message")
    op.drop_table("message")
    op.drop_index("uq_conversation_person_channel_open", table_name="conversation")
    op.drop_index("ix_conversation_bot_configuration_id", table_name="conversation")
    op.drop_index("ix_conversation_assignee_user_id", table_name="conversation")
    op.drop_index("ix_conversation_person_id", table_name="conversation")
    op.drop_index("ix_conversation_channel_account_id", table_name="conversation")
    op.drop_table("conversation")
```

**Cadena de revids** (todos ≤32): `0014_crm_customer_lifecycle` (27) → `0015_conv_channel_account` (25) → `0016_conv_threads` (17). F0, F3 y F4 no llevan migración (F0 = solo seed/skeleton; F3 = las tablas ya existen; F4 = `message_attachment` ya existe desde F2, solo procesa media).

> **Nota dialect-agnóstica (modelos vs migración)**: los **modelos** declaran el índice parcial con `postgresql_where + sqlite_where` (para que el smoke `create_all` lo reproduzca en sqlite); la **migración** escribe solo `postgresql_where` (la migración solo corre en Postgres). Es el patrón real shipped en crm (`crm/models/person_contact_identifier.py` usa ambos; `alembic/versions/0011_crm_person.py` usa solo `postgresql_where`).

---

## 13. Checklist de implementación (mapeado a fases F0–F3 + F4 diferida)

### F0 — Prep (sin migración; solo seed + skeleton)
- [ ] Agregar los 12 permisos `CONVERSATIONS` a `app/core/seed.py:SEED_PERMISSIONS` (ya canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md); no redefinir).
- [ ] Verificar que `_seed_role` aplique el subset `ASESOR` (los códigos `CONVERSATIONS_*`/`MESSAGES_*`/`MY_CONVERSATIONS_READ`/`MENU-CONVERSATIONS`) — el filtro por código los toma al existir el permiso (`DOCTOR` sin perms en conversations).
- [ ] Crear el skeleton `backend/app/modules/conversations/{enums,models,schemas,repositories,services,routers}/` (con `enums.py` completo + docstrings inertes). NO registrar en `app/modules/__init__.py` ni `main.py` todavía (lo cablea F1).
- [ ] (Frontend F0) nav grupo "Conversaciones" (`MENU-CONVERSATIONS`) + `endpoints.ts` (bloque conversations) + `types/conversations.types.ts` (espejo completo, inerte) — ver [`frontend.md`](frontend.md).
- [ ] Smoke: login admin → el JWT contiene los 12 permisos CONVERSATIONS.

### F1 — ChannelAccount + secret_resolver (migración `0015_conv_channel_account`)
- [ ] `models/channel_account.py` (UNIQUE parcial dialect-agnóstico) + migración `0015_conv_channel_account` (`down_revision="0014_crm_customer_lifecycle"`).
- [ ] `schemas/channel_account.py` (`Create/Update/Item/Detail/Option`; `Detail` NUNCA expone el secreto, expone `secret_name` + flags `has_secret`/`has_verify_token`).
- [ ] `repositories/channel_account.py` (`ALLOWED_FIELDS` solo columnas reales, `get_by_external_id`, `list_active`).
- [ ] `services/channel_account.py` (CRUD + guard `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` + `get_credentials`).
- [ ] **`app/core/secrets.py`** (SDK Secret Manager async + cache TTL + fallback env, lazy init) + Settings nuevos (`GCP_PROJECT_ID`, `WHATSAPP_*`) + dep `google-cloud-secret-manager` en `pyproject.toml`.
- [ ] Registrar `conversations` en `app/modules/__init__.py` + aggregator router (`/channel-accounts/*`) en `main.py`.
- [ ] `routers/channel_account.py` (CRUD + `/active` antes de `/{id}`).
- [ ] (Frontend F1) `/conversaciones/canales` (DataTable + drawer; secreto = "configurado/sin configurar") — ver [`ui.md`](ui.md).
- [ ] Test: crear ChannelAccount; duplicado `(channel_type, external_identifier)` vivo → `409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN`; soft-delete → se puede recrear; `Detail` no trae el secreto; `get_credentials` con `ENV_NAME=dev` toma el fallback env (no llama Secret Manager).

### F2 — Inbound pipe (migración `0016_conv_threads`)
- [ ] `models/conversation.py` (UNIQUE parcial 1-open) + `message.py` (UNIQUE parcial external_id, JSONB variant) + `message_attachment.py` (modelado; col `metadata`) + `conversation_assignment_log.py` + migración `0016_conv_threads` (`down_revision="0015_conv_channel_account"`) **con la FK aditiva** `lead_activity.related_conversation_id → conversation.id`.
- [ ] `schemas/conversation.py` (`ConversationListItem`/`ConversationDetail`/`ConversationAssignmentLogItem`/Take/Release) + `schemas/message.py` (`MessageItem`/`MessageAttachmentItem`/`MessageSendRequest`).
- [ ] `repositories/{conversation,message,message_attachment,conversation_assignment_log}.py` (`get_open`, `has_other_open`, `list_inbox` con extra_filters; `get_by_external_id`/`append`/`list_for_conversation`; `attachments_map`; `get_current_open`/`list_for_conversation`) + batch maps de denorm.
- [ ] `app/routers/__init__.py` + `app/routers/webhooks.py` (GET verify + POST inbound con firma) registrado en `main.py`.
- [ ] `services/webhook_processor/whatsapp.py` (`verify_signature` HMAC, `process_inbound` parse + `find_or_create_open` + `persist_inbound` + `apply_status`).
- [ ] `services/conversation.py` (`find_or_create_open` con auto-asignación vía `crm.lead_assignment_repository.advisor_map` + fallback unassigned) + `services/message.py` (`persist_inbound`, `apply_status`).
- [ ] **crm hardening**: advisory lock en `find_by_identifier_or_create` (dialect-guard postgresql; sqlite no-op).
- [ ] `routers/conversation.py` (`/list`, `/{id}`, `/{id}/messages/list`) + `routers/me.py` — solo recibir/ver (read).
- [ ] (Frontend F2) inbox 2-paneles (recibir + ver, read; polling) — ver [`ui.md`](ui.md).
- [ ] Test: webhook con firma válida crea Person (vía crm) + Conversation auto-asignada al dueño del lead (o unassigned) + Message inbound (unread_count=1); reenvío del mismo `external_id` → dedup no-op (unread no incrementa); firma inválida → `403 WEBHOOK_SIGNATURE_INVALID`; GET verify con token correcto devuelve el challenge; cuenta inexistente → 404; `statuses[]` marca delivered/read.

### F3 — Handoff + outbound (sin migración nueva)
- [ ] `services/conversation.py`: `take`/`release`/`close`/`reopen`/`mark_read` con los invariantes + `ConversationAssignmentLog` writes (`_close_current_log`/`_open_assignment_log`/`_reassign`).
- [ ] **crm `lead_activity.log` extendido** (`related_conversation_id`) + emisión `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED`.
- [ ] `services/message.py`: `send_outbound` real (Meta Graph API via `get_credentials`; persiste fallido + 200).
- [ ] `routers/conversation.py`: take/release/close/reopen/mark-read + `POST /{id}/messages`.
- [ ] (Frontend F3) composer + controles de handoff + `/conversaciones/mis-conversaciones` — ver [`ui.md`](ui.md).
- [ ] Test: `take` asigna actor + resetea unread + emite `CONVERSATION_TAKEN` (related_conversation_id) + cierra el log vigente y abre uno nuevo; `release` a unassigned emite `CONVERSATION_RELEASED`; `close` cierra log + `closed_at`; `reopen` con otra open → `409 CONVERSATION_ALREADY_OPEN`; `send_outbound` por no-assignee → `403 NOT_CONVERSATION_ASSIGNEE`; conversación cerrada → `400 CONVERSATION_NOT_OPEN`; envío fallido → 200 con message `failed`; los eventos `CONVERSATION_*` NO son editables por el composer del asesor (404 vía `crm._get_editable_owned`).

### F4 — Adjuntos/media (DIFERIDA)
- [ ] Processing de `MessageAttachment` (download/storage — lazy proxy vs GCS se re-confirma), inbound/outbound media en `webhook_processor`/`send_outbound`, `attachments_map` real, render UI. Fuera del MVP inicial.

> Flujo de cada fase = el de la metodología: leer fichas → backend e2e + smoke (sqlite create_all, RESULT=PASS+conteo a stdout) → frontend e2e (subagente contexto fresco) → tsc+build → review adversaria (Workflow 4 dims → verificación por hallazgo) → commit limpio (sin Co-Authored-By) → ff develop→qa → QA E2E con limpieza → **gate usuario (AskUserQuestion separado del merge)** → prod → PROD read-only → actualizar memoria. Backend venv: `backend/.venv/Scripts/{python,ruff,mypy}.exe`.

---

## 14. Notas operativas (gotchas)

- **revid Alembic ≤ 32 chars** (clinic F3 reventó con 34 → StringDataRightTruncation). `0015_conv_channel_account`=25, `0016_conv_threads`=17. ✔
- **Glob NO ve `app/modules/**`** (OneDrive dehydration) → Read con paths exactos.
- **`metadata` es atributo reservado** en la `Base` declarativa de SQLAlchemy → la columna de `MessageAttachment` se nombra `"metadata"` pero el atributo Python es `attachment_metadata` (`mapped_column("metadata", ...)`); el contrato JSON expone `metadata`.
- **El smoke (`create_all`, no alembic) NO ejercita la migración** (JSONB / ALTER ADD FK / partial index con `WHERE status='open'` son Postgres) → el `sqlite_where` en los modelos reproduce el índice parcial en el smoke; la FK aditiva y JSONB se validan vía QA E2E sobre Postgres. La review adversaria caza el drift Zod↔Pydantic y bugs de render que el smoke no ve (lección crm).
- **`raw_body` para la firma**: leer `await request.body()` ANTES de parsear JSON; re-serializar cambia los bytes y rompe el HMAC de Meta.
- **PowerShell 5.1**: no `&&`, `$pid` reservado (usar `$srvPid`), no `-SkipHttpErrorCheck`, IWR cuelga→curl.
- **`app/modules/__init__.py` hoy NO incluye `staff`** (tolerado por migraciones manuales) — incluir `conversations` igual (F1) para que Alembic/relationships lo registren.
- **`httpx`**: si no está en deps de runtime (solo test), agregarlo al `pyproject.toml` para `_meta_send_text` (cliente async outbound).
- **1 comando por call** en git/deploy; verificar que el verificador CORRIÓ (RESULT=PASS + conteo); gate de prod = AskUserQuestion separado del merge.
- **TZ**: `last_message_at`/`opened_at` se guardan tz-aware UTC (`utc_now()`); el render de "Hoy/Ayer" + day-groups del inbox va client-only (lección TZ recurrente — SSR en UTC desfasa el día en TZ negativas).

---

## 15. Decisiones para ADRs / consolidación

- **ADR-004 (update, mantener Accepted, "act. 2026-06-02")**: corregir la afirmación errónea sobre Secret Manager ("cliente ya configurado" → en realidad inyección por env vía `--set-secrets`; ahora SDK runtime, ver ADR-010); PATCH→PUT; agregar las decisiones refinadas: auto-asignación al dueño del lead (con fallback unassigned), texto-primero en adjuntos, webhook síncrono en el MVP (BackgroundTasks/cola diferido a bots), emisión solo `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED` (no `MESSAGE_SENT` por-mensaje), hardening de `find_by_identifier_or_create` con advisory lock, FK aditiva `related_conversation_id`.
- **ADR-010 (nuevo, Accepted)**: "Resolución de secretos por-cuenta vía Secret Manager SDK en runtime (cacheado)". Contexto: el template inyecta secretos fijos por env (deploy-time); las credenciales por-ChannelAccount necesitan resolución dinámica para multi-cuenta sin redeploy. Decisión: SDK `google-cloud-secret-manager` + `app/core/secrets.py` con cache TTL + fallback env (local/test). Alternativas: inyección por env (descartada: 1 número por deploy), columna cifrada en BD (descartada: secreto en backups). Reusable por futuros módulos con secretos por-tenant/cuenta.
- **Diagramas**: regenerar `er-conversations.puml` (anotar `channel_type` = reuse `crm.ChannelType`; `bot_configuration_id`/`default_campaign_id` = forward sin constraint ADR-009; FK aditiva `lead_activity → conversation`) y `class-backend-conversations.puml` (secret_resolver en `app.core`; webhook_processor; auto-asignación; helpers crm consumidos). PATCH→PUT en cualquier referencia.
- **Overview viejo**: borrar `docs/modules/conversations.md` (consolidado en el README) y repuntar TODOS sus links (`grep "modules/conversations.md"`) al `conversations/README.md`.
- **Memoria**: crear `project_medisage_conversations_plan.md` + puntero en MEMORY.md.
