# Módulo `conversations` — Backend deep-dive

> **Última actualización**: 2026-06-03 (rediseño CQRS: stream de mensajes en Firestore — ver ADR-011)
> **Audiencia**: developer implementando `backend/app/modules/conversations/` + el router top-level nuevo `backend/app/routers/webhooks.py` + los cross-cutting `backend/app/core/secrets.py` y `backend/app/core/firestore.py`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`../../decisions/ADR-004-conversation-channel-account.md`](../../decisions/ADR-004-conversation-channel-account.md) (Conversation + ChannelAccount, **revisado**: Message YA NO es entidad Postgres relacional), [`../../decisions/ADR-009-forward-fk-deferred-cross-module.md`](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (FKs forward diferidas), [`../../decisions/ADR-010-runtime-secret-resolution.md`](../../decisions/ADR-010-runtime-secret-resolution.md) (resolución de secretos por-cuenta en runtime — **nuevo**), [`../../decisions/ADR-011-firestore-message-stream-cqrs.md`](../../decisions/ADR-011-firestore-message-stream-cqrs.md) (**stream de mensajes en Firestore — CQRS read-model + Transactional Outbox + Custom Tokens — la decisión arquitectónica central de este módulo**), [`_seed-and-roles.md`](../_seed-and-roles.md) (los 12 permisos `CONVERSATIONS` + roles `ASESOR`/`DOCTOR`/`ADMIN`), y los deep-dives molde [`../crm/backend.md`](../crm/backend.md) (gold-standard: denormalización batch sin N+1, `find_by_identifier_or_create`, `lead_activity.log`, ADR-009, migraciones manuales) y [`../staff/backend.md`](../staff/backend.md) (`/me`, helpers aditivos a `admin`).

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
> 8. **Mixins del template** (`app.shared.base_model`): `PrimaryKeyMixin` (`id` varchar(36)), `ActiveMixin` (`active`), `SoftDeleteMixin` (`deleted_at`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **`MessageOutbox`/`ConversationAssignmentLog` NO llevan `SoftDeleteMixin`** — son durables/audit honesto (la cola transaccional no se soft-deletea; el historial de handoff es inmutable); "borrar" un log o un registro de outbox no es una operación de negocio. **`MessageOutbox` además NO hereda `PrimaryKeyMixin`** (su `id` es el `mid` provisto por el caller, `varchar(255)` — ver §3).

`conversations` es el **módulo #5** de medisage (catalog→clinic→staff→crm **COMPLETOS en prod**; sigue conversations; luego bots #6, scheduling #7, marketing #8). Es el **dueño del pipe de mensajería multicanal**: recibe inbound desde webhooks de proveedores (WhatsApp Cloud API en el MVP), valida la firma, persiste, identifica al `Person` vía `crm.find_by_identifier_or_create`, auto-asigna la conversación al dueño del lead y la deja en la bandeja del asesor; del lado saliente envía mensajes reales contra Meta Graph API. Decisiones nuevas que este doc materializa: **ADR-011** (stream de mensajes en Firestore — CQRS read-model), **ADR-010** (resolución de secretos por-cuenta vía Secret Manager SDK en runtime, cacheado) y **ADR-004 revisado**.

> **🔑 Arquitectura CQRS de mensajes (ADR-011) — leer ANTES de los models.** Los **mensajes NO se persisten en Postgres**: viven en **Cloud Firestore (Native mode)** como **read-model en tiempo real**. Postgres es el **control plane / fuente de verdad** (`channel_account`, `conversation`, `conversation_assignment_log`, **`message_outbox`**); Firestore es el **data plane** (proyección eventual del stream de mensajes). El puente es un **Transactional Outbox**: la TX de Postgres escribe a `message_outbox` (durable, idempotente por `id=mid`), y un **relay SÍNCRONO** (`message_service.relay_outbox(db)`, en el mismo request y la misma sesión, antes del 200) lo replica a Firestore con el Firebase **Admin SDK** (`set(doc_id=mid)` → create-if-absent). (`BackgroundTasks` se descartó por no proyectar confiablemente en Cloud Run; un sweep/Cloud Task reintenta las filas `failed` vía `relay_outbox_in_new_session`.) El **browser solo LEE** Firestore vía **listeners real-time** autenticados con **Custom Tokens** minteados por el backend + **Security Rules** que espejan el RBAC (`allowed_reader_ids` + `can_read_all`); TODA escritura/lógica sigue 100% server-side. Esto preserva el principio del template "el browser no muta el backend / JWT server-side / RBAC" — solo agrega un canal de **lectura** real-time gobernado por las reglas. Ver §3-bis (`app/core/firestore.py`), §3-ter (data model Firestore + `firestore.rules`), y la reescritura de `services/message.py` en §6.

---

## 1. Estructura de archivos a crear

```
backend/app/
├── core/
│   ├── secrets.py                        # NUEVO cross-cutting: secret_resolver (SDK Secret Manager + cache TTL + fallback env)  ── F1
│   └── firestore.py                      # NUEVO cross-cutting: Firebase Admin SDK (init lazy ADC, get_db, mint_custom_token, doc writers)  ── F1
├── routers/                              # NUEVO paquete top-level (hoy NO existe app/routers/)
│   ├── __init__.py                       # docstring; no aggregator (cada router top-level se incluye suelto en main.py)
│   └── webhooks.py                       # router top-level SIN JWT: GET verify + POST inbound de WhatsApp  ── F2
└── modules/conversations/
    ├── __init__.py
    ├── enums.py                          # ConversationStatus, AssigneeType, MessageDirection, SenderType, ContentType, AttachmentType, MessageExternalStatus
    ├── models/
    │   ├── __init__.py                   # importa todos los modelos Postgres (registro en Base.metadata)
    │   ├── channel_account.py            # ── F1
    │   ├── conversation.py               # ── F2 (control plane / fuente de verdad)
    │   ├── message_outbox.py             # ── F2 (cola transaccional Postgres→Firestore; reemplaza message/message_attachment como tablas)
    │   └── conversation_assignment_log.py # ── F2
    │                                     # NB: NO hay models/message.py ni models/message_attachment.py — el mensaje vive en Firestore (CQRS, ADR-011)
    ├── schemas/
    │   ├── __init__.py
    │   ├── channel_account.py            # ChannelAccountCreate/Update/Item/Detail/Option  (Detail NUNCA expone el secreto)
    │   ├── conversation.py               # ConversationListItem, ConversationDetail, Take/Release requests, ConversationAssignmentLogItem
    │   ├── message.py                    # MessageItem, MessageAttachmentItem, MessageSendRequest (contrato API + shape del doc Firestore)
    │   └── realtime.py                   # RealtimeTokenResponse (token + firebase_config?)
    ├── repositories/
    │   ├── __init__.py
    │   ├── channel_account.py            # get_by_external_id, list/active
    │   ├── conversation.py               # get_open, find/list_inbox, ALLOWED_FIELDS, denorm batch maps
    │   ├── message_outbox.py             # enqueue (ON CONFLICT DO NOTHING), list_pending, mark_done/mark_failed
    │   └── conversation_assignment_log.py # current_open, list_for_conversation, close_current/open_new
    │                                     # NB: NO hay repositories/message.py ni message_attachment.py — los mensajes se leen de Firestore (Admin SDK)
    ├── services/
    │   ├── __init__.py
    │   ├── channel_account.py            # CRUD + get_credentials(ca) (delega a app.core.secrets / fallback env)
    │   ├── conversation.py               # find_or_create_open (auto-asignación), take/release/close/reopen/mark_read (+ enqueue conversation_upsert)
    │   ├── message.py                    # persist_inbound (outbox+denorm), relay_outbox (→Firestore), send_outbound (Meta+Firestore), apply_status (doc Firestore), list_messages (fallback Firestore)
    │   ├── realtime.py                   # mint_token (claims scope/is_advisor/can_read_all desde el RBAC)
    │   └── webhook_processor/
    │       ├── __init__.py
    │       └── whatsapp.py               # verify_signature, process_inbound, process_status (cohesión por canal)
    └── routers/
        ├── __init__.py                   # aggregator: prefix="/conversations"
        ├── channel_account.py            # /channel-accounts/*
        ├── conversation.py               # /list, /{id}, take/release/close/reopen/mark-read, /messages/*
        ├── realtime.py                   # /realtime/token (mint Custom Token Firebase)
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
from app.modules.conversations.routers.realtime import router as realtime_router

router = APIRouter(prefix="/conversations")
router.include_router(channel_account_router)  # /channel-accounts/*
router.include_router(realtime_router)         # /realtime/token  (declarado antes de /{id} para no chocar)
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
> ⚠ **JSONB variant**: `message_outbox.payload` usa `JSON().with_variant(JSONB(), "postgresql")` (idéntico a `crm.lead_activity.payload`): JSONB en Postgres (prod), JSON en sqlite (el smoke usa `create_all`, no alembic; JSONB puro no serializa dicts en sqlite). La migración escribe `JSONB` (solo corre en Postgres). (El `provider_payload` y los `attachments[]` del mensaje YA NO son columnas Postgres — son campos del doc Firestore; ver §3-ter.)

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

> **🔑 NO hay `models/message.py` ni `models/message_attachment.py`.** El stream de mensajes (incluidos sus adjuntos) NO es una tabla Postgres: vive en Firestore como read-model (CQRS, ADR-011). El contrato de cada mensaje (los campos `direction`/`sender_type`/`content_type`/`external_id`/`external_status`/`sent_at`/`delivered_at`/`read_at`/`failed_at`/`failure_reason`/`provider_payload`/`attachments[]`/`created_at`) vive ahora como **doc Firestore** (§3-ter) y como **schema Pydantic** (§4, contrato de la API fallback). La idempotencia que antes daba el UNIQUE parcial `(conversation_id, external_id)` ahora la da `message_outbox.id` UNIQUE (= `mid`) + el doc-id `mid` en Firestore (doble dedup). La tabla Postgres que SÍ aparece es la cola transaccional `message_outbox`.

### `models/message_outbox.py` — tabla `message_outbox` — A·T (SIN PrimaryKeyMixin ni SoftDelete — cola durable)

```python
"""
MessageOutbox = cola transaccional durable Postgres→Firestore (Transactional Outbox,
ADR-011). Resuelve el dual-write Postgres↔Firestore SIN transacción distribuida: la TX
de control-plane escribe aquí (misma tx, atómico); un relay aparte la replica a Firestore
con el Admin SDK y la marca `done`. SIN SoftDeleteMixin (es infraestructura, no entidad de
negocio). NB: tampoco hereda `PrimaryKeyMixin` — el `id` ES el `mid` del mensaje (wamid
inbound / uuid outbound), varchar(255), provisto por el caller (no autogen) → UNIQUE da
idempotencia: el `INSERT ... ON CONFLICT (id) DO NOTHING` deduplica el reenvío del webhook
de Meta, y el `unread_count++` solo corre si el insert fue nuevo. `op` distingue
message_create / message_status / conversation_upsert. `payload` (JSONB variant) = el doc
EXACTO a escribir en Firestore. Índice (status, created_on) para que el relay barra los
pendientes en orden.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, TimestampMixin


class MessageOutbox(ActiveMixin, TimestampMixin, Base):
    __tablename__ = "message_outbox"
    __table_args__ = (
        # El relay barre los pendientes en orden de llegada.
        Index("ix_message_outbox_status_created", "status", "created_on"),
    )

    # NB: NO hereda `PrimaryKeyMixin` (que forzaría varchar(36) + autogen uuid): el `id` es
    # el `mid` del mensaje (wamid inbound / uuid outbound) — varchar(255), porque el wamid de
    # Meta es más largo que un uuid — y lo PROVEE el caller, nunca se autogenera. UNIQUE (es
    # PK) → ON CONFLICT (id) DO NOTHING deduplica. Para op=conversation_upsert el id es un
    # uuid sintético (no hay mid de mensaje).
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    # message_create | message_status | conversation_upsert
    op: Mapped[str] = mapped_column(String(40), nullable=False)
    # El doc EXACTO a escribir en Firestore (snake_case, mismo shape que MessageItem /
    # el conversation doc). JSON en sqlite (smoke), JSONB en Postgres.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    # pending | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

> **`id = mid` (no autogenerado; NO hereda `PrimaryKeyMixin`).** A diferencia del resto de los modelos del template, `MessageOutbox` **no** hereda `PrimaryKeyMixin` (que daría un `id` `varchar(36)` autogenerado con `generate_uuid()`): declara su propio `id: Mapped[str] = mapped_column(String(255), primary_key=True)` y lo provee el caller con el `mid` del mensaje (`wamid` para inbound — viene de Meta; `uuid` para outbound — lo genera el service). Eso convierte la PK en la clave de idempotencia: `INSERT ... ON CONFLICT (id) DO NOTHING` (Postgres) descarta el reenvío del webhook, y el mismo `mid` es el doc-id en Firestore (`set` create-if-absent) → doble dedup. Para `op=conversation_upsert` (que no tiene `mid` de mensaje) el `id` es un uuid sintético; lo que importa ahí es el `conversation_id` del payload (el doc-id Firestore = `cid`, idempotente por overwrite). El `id` se crea **directamente como `varchar(255)`** en la migración 0016 (no es un `varchar(36)` ampliado) para alojar el `wamid` de Meta (más largo que un uuid).
> **Estados**: `pending` (recién encolado) → `done` (relay escribió a Firestore OK) → `failed` (agotó reintentos; `last_error`/`attempts` para diagnóstico; un sweep/Cloud Task lo reintenta). El relay es idempotente (`set(doc_id)`), así que reprocesar un `done` no duplica nada — la durabilidad prima sobre el "exactly once".

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
before children (conversation → message_outbox, conversation_assignment_log). NB: el
stream de mensajes NO es Postgres (vive en Firestore, CQRS/ADR-011) → NO hay Message ni
MessageAttachment acá; lo que se registra es message_outbox (cola transaccional).
"""

from app.modules.conversations.models.channel_account import ChannelAccount
from app.modules.conversations.models.conversation import Conversation
from app.modules.conversations.models.message_outbox import MessageOutbox
from app.modules.conversations.models.conversation_assignment_log import (
    ConversationAssignmentLog,
)

__all__ = [
    "ChannelAccount",
    "Conversation",
    "MessageOutbox",
    "ConversationAssignmentLog",
]
```

> **Lazy strategy**: NO se declaran `relationship(...)` cross-módulo (a `Person`/`User`) — consistente con el patrón crm "sin relationship cross-módulo, todo por FK column + batch maps". Dentro del módulo tampoco se declaran relationships (los hijos Postgres se consultan por `conversation_id` directamente y se denormalizan vía batch maps), para mantener el modelo plano y los reads explícitos (sin N+1 silencioso). `ConversationDetail.assignment_history` se arma con una query de repo dedicada, no con lazy-load. Los **mensajes** (`MessageItem.attachments` incluido) NO se cargan de Postgres: se leen de Firestore — en vivo desde el cliente (path primario) o vía Admin SDK server-side en el fallback `list_messages` (§6).

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
    credentials_configured: bool      # = secret_name is not None (espejo de types.ts)
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

> **`ChannelAccountDetail` NUNCA expone el secreto.** El `access_token`/`app_secret` viven solo en GCP Secret Manager; el API expone `secret_name` (el nombre del recurso) + los flags `credentials_configured`/`has_verify_token`. `get_credentials(ca)` (server-only) es el único camino al valor. El frontend muestra "configurado / sin configurar" (no el valor). `webhook_verify_token` SÍ se expone porque no es un secreto duro (Meta lo envía en claro en el GET de verificación y solo lo comparamos).

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
    """Shape de un adjunto del mensaje. Es el shape del sub-objeto `attachments[]` del
    DOC Firestore (NO una tabla Postgres). Sin processing en el MVP → en la práctica lista
    vacía hasta F4 (texto primero). En F4 cada adjunto apunta a un binario en GCS (url
    firmada)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    message_id: str
    attachment_type: AttachmentType
    url: str | None              # F4: URL firmada de GCS
    mime_type: str | None
    size_bytes: int | None
    duration_sec: int | None
    latitude: float | None
    longitude: float | None
    address_label: str | None
    original_filename: str | None
    external_media_id: str | None
    metadata: dict | None = None  # campo libre del doc Firestore


class MessageItem(BaseModel):
    """Contrato del mensaje. DOBLE propósito: (1) shape del DOC Firestore
    `conversations/{cid}/messages/{mid}` (snake_case — alineado a propósito con el
    contrato de la API; el browser lo lee tal cual vía onSnapshot); (2) shape del envelope
    del endpoint FALLBACK `POST /{id}/messages/list` (que lee Firestore server-side vía
    Admin SDK). NO mapea una tabla Postgres. `id` = el `mid` (= doc-id Firestore =
    wamid/uuid). `created_on` ↔ `created_at` del doc (el campo del doc se llama
    `created_at`; el service lo mapea al schema)."""

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

### `schemas/realtime.py`

```python
from __future__ import annotations

from pydantic import BaseModel


class RealtimeTokenResponse(BaseModel):
    """Respuesta de POST /conversations/realtime/token. `token` = Firebase Custom Token
    (string JWT firmado por el backend vía Admin SDK; lo consume signInWithCustomToken en
    el browser). `firebase_config` = config PÚBLICA del Firebase project (apiKey/projectId/
    etc. — NO son secretos, son config) para que el front inicialice el SDK; opcional si el
    front la trae de sus NEXT_PUBLIC_FIREBASE_* envs."""

    token: str
    firebase_config: dict | None = None
```

> **El Custom Token NO es un secreto persistente**: es de vida corta (lo intercambia el browser por un ID token de 1 h vía `signInWithCustomToken`), gateado por el RBAC del template (el endpoint exige `CONVERSATIONS_READ` o `MY_CONVERSATIONS_READ`) y minteado server-side. La `firebase_config` (apiKey, projectId, etc.) es **config pública** del proyecto Firebase, no un secreto — vive en `NEXT_PUBLIC_FIREBASE_*` (front) y puede repetirse en la respuesta por conveniencia.

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

### `repositories/message_outbox.py`

> Reemplaza a `repositories/message.py` + `repositories/message_attachment.py` (que YA NO existen — los mensajes se leen de Firestore, no de Postgres). El outbox NO se pagina ni se filtra desde el front (`ALLOWED_FIELDS = set()`): es infraestructura interna. La idempotencia inbound se delega al **`ON CONFLICT (id) DO NOTHING`** del enqueue (raw SQL Postgres / catch en sqlite), no a un `get_by_external_id` previo.

```python
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert


class MessageOutboxRepository(BaseRepository[MessageOutbox]):
    ALLOWED_FIELDS: set[str] = set()  # infraestructura interna; nunca filtrable desde el front

    def __init__(self) -> None:
        super().__init__(MessageOutbox)

    async def enqueue(
        self, db: AsyncSession, *, id: str, conversation_id: str, op: str,
        payload: dict, actor_id: str,
    ) -> bool:
        """Encola una operación durable. IDEMPOTENTE por PK: ON CONFLICT (id) DO NOTHING
        (Postgres). Devuelve True si insertó algo NUEVO, False si el id ya existía (reenvío
        de Meta dedup). El caller usa el bool para decidir si incrementa unread_count /
        actualiza last_message_* (solo en el insert nuevo). En sqlite (smoke) se emula con
        un get-then-insert (single-thread; sin carrera)."""
        now = utc_now()
        values = dict(
            id=id, conversation_id=conversation_id, op=op, payload=payload,
            status="pending", attempts=0, active=True,
            created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
        )
        if db.bind.dialect.name == "postgresql":
            stmt = pg_insert(MessageOutbox).values(**values).on_conflict_do_nothing(
                index_elements=[MessageOutbox.id]
            )
            result = await db.execute(stmt)
            return result.rowcount > 0
        # sqlite (smoke): get-then-insert; sin carrera (single-thread).
        existing = await db.get(MessageOutbox, id)
        if existing is not None:
            return False
        await db.execute(insert(MessageOutbox).values(**values))
        return True

    async def list_pending(self, db: AsyncSession, *, limit: int = 100) -> list[MessageOutbox]:
        """El relay barre los pendientes por (status, created_on)."""
        result = await db.execute(
            select(MessageOutbox)
            .where(MessageOutbox.status == "pending")
            .order_by(MessageOutbox.created_on.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_done(self, db: AsyncSession, outbox_id: str) -> None:
        await db.execute(
            update(MessageOutbox).where(MessageOutbox.id == outbox_id).values(
                status="done", processed_on=utc_now()
            )
        )

    async def mark_failed(self, db: AsyncSession, outbox_id: str, *, error: str) -> None:
        await db.execute(
            update(MessageOutbox).where(MessageOutbox.id == outbox_id).values(
                status="failed", attempts=MessageOutbox.attempts + 1,
                last_error=error[:500], processed_on=utc_now(),
            )
        )


message_outbox_repository = MessageOutboxRepository()
```

> **`enqueue` devuelve el bool de novedad** — es el corazón de la idempotencia inbound (§2/§7 del brief). El webhook llama `enqueue(op=message_create, id=wamid, ...)`; si devuelve `False` (reenvío de Meta para el mismo `wamid`), el processor NO incrementa `unread_count` ni reescribe `last_message_*` ni encola el `conversation_upsert`. **No** hay `get_by_external_id` previo: el `ON CONFLICT` lo resuelve atómicamente en un solo round-trip. Los mensajes en sí (lectura) viven en Firestore, no acá.

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
> Cero N+1. `_to_list_item` recibe esos maps como kwargs (igual que `crm._to_item`). `ConversationDetail.assignment_history` con `list_for_conversation` + un `get_audit_info_map` sobre todos los `*_user_id` de los logs. **Los mensajes (y sus `attachments[]`) NO se denormalizan desde Postgres**: el hilo se lee de Firestore — en vivo desde el cliente (path primario, `onSnapshot`) o vía el fallback `message.list_messages` (Admin SDK server-side; §6). El `sender_user` (UserAuditInfo) del mensaje se hidrata en el momento de escribir el doc (el service ya conoce al actor) o en el fallback con un `get_audit_info_map` sobre los `sender_user_id` de la página.

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
    # reload + audit users → _to_detail (credentials_configured = secret_name is not None; jamás el valor)
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
            code="CHANNEL_CREDENTIALS_MISSING",  # BadRequestException → 400 (ver §9; server-side, no se surface directo)
        )
    return creds
```

> **`CHANNEL_CREDENTIALS_MISSING`**: el código lo emite como **`BadRequestException` (400)** (el template no tiene excepción de dominio 500; `BadRequestException` lleva el `code`). Conceptualmente es una mala config del operador, pero el status es **secundario**: `get_credentials` se invoca SOLO server-side (F2/F3) y NUNCA se surface directo — en el webhook la verificación de firma decide 403/200 a Meta; en el outbound se persiste el mensaje fallido. `phone_number_id` se prefiere de la columna `ca.phone_number_id` (practicidad de la URL) y cae al env solo en fallback.

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
    # Crea el doc conversations/{cid} en Firestore (con allowed_reader_ids) — persist_inbound
    # también lo re-encola tras el primer mensaje (idempotente por overwrite).
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
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
    # Reflejar el nuevo assignee/allowed_reader_ids/unread en el doc Firestore.
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
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
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)  # refleja assignee/allowed_reader_ids
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
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)  # status=closed en Firestore
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
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)  # status=open en Firestore
    await db.flush()
    return await _reload_detail(db, conv)


async def mark_read(db, conversation_id: str, *, actor_id: str) -> SingleResponse[ConversationDetail]:
    conv = await _get_or_404(db, conversation_id)
    conv.unread_count = 0
    conv.updated_by = actor_id; conv.updated_on = utc_now()
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)  # unread_count=0 en Firestore
    await db.flush()
    return await _reload_detail(db, conv)
```

> **`_reassign` / `_open_assignment_log` / `_close_current_log`** son helpers privados que materializan el invariante "una sola fila vigente": `_close_current_log` hace `UPDATE ... SET ended_at=now WHERE conversation_id=? AND ended_at IS NULL`; `_open_assignment_log` inserta la nueva fila vigente; `_reassign` = `_close_current_log` + `_open_assignment_log` con el `from_*` tomado del estado actual de la conversación. Todo en la tx del request.
> **Emisión a la timeline de crm (decisión §1)**: SOLO `CONVERSATION_TAKEN` (take) y `CONVERSATION_RELEASED` (release), vía `crm.lead_activity.log(..., related_conversation_id=conv.id)`. **NO** `MESSAGE_SENT` por-mensaje (evita inundar el timeline lead-céntrico y la escritura cross-módulo en el hot path del envío). Estos eventos NO son de `crm.ADVISOR_ACTIVITY_TYPES` → `crm._get_editable_owned` los rechaza con 404 → **audit trail inmutable** (el asesor no los puede editar/borrar). Solo se emiten si `conv.person_id is not None`.

> **🔑 Reflejo del conversation doc en Firestore (CQRS).** **`take`/`release`/`close`/`reopen`/`mark_read`** — además de mutar la fila Postgres y el `ConversationAssignmentLog` — **encolan un `conversation_upsert`** al outbox vía el helper `enqueue_conversation_upsert(db, conv, actor_id=...)`, para que el doc `conversations/{cid}` de Firestore refleje el nuevo `status`/`assignee_user_id`/`allowed_reader_ids`/`unread_count`. Esto es lo que actualiza en vivo el inbox del cliente (si usa la collection live) **y** lo que recomputa `allowed_reader_ids` (= `[assignee_user_id]` + supervisores con `CONVERSATIONS_READ`) — la pieza que gobierna quién puede leer el hilo según las Security Rules (§3-ter). El helper arma el doc liviano y llama `message_outbox_repository.enqueue(op="conversation_upsert", id=generate_uuid(), conversation_id=conv.id, payload=conversation_doc, ...)`; el relay lo escribe con `upsert_conversation_doc` (set/merge por `cid`, idempotente por overwrite). `allowed_reader_ids` lo computa el helper consultando los user_ids con `CONVERSATIONS_READ` (vía un helper aditivo de `admin`, ver §8) + el `assignee_user_id`.

```python
async def enqueue_conversation_upsert(db, conv: Conversation, *, actor_id: str) -> None:
    """Encola el espejo liviano del Conversation a Firestore (conversations/{cid}). Recalcula
    allowed_reader_ids = [assignee_user_id si advisor] + [supervisores con CONVERSATIONS_READ].
    Llamado por find_or_create_open / persist_inbound / take/release/close/reopen/mark_read."""
    reader_ids = await admin.user_repository.list_user_ids_with_permission(db, "CONVERSATIONS_READ")
    if conv.assignee_type == AssigneeType.advisor.value and conv.assignee_user_id:
        reader_ids = list({*reader_ids, conv.assignee_user_id})
    person_name = ...  # batch/cache: full_name de la Person (denormalizado, para el inbox live)
    doc = {
        "status": conv.status, "assignee_user_id": conv.assignee_user_id,
        "allowed_reader_ids": reader_ids, "channel_account_id": conv.channel_account_id,
        "person_name": person_name, "person_id": conv.person_id,
        "last_message_at": conv.last_message_at, "last_message_preview": conv.last_message_preview,
        "unread_count": conv.unread_count, "updated_at": utc_now(),
    }
    await message_outbox_repository.enqueue(
        db, id=generate_uuid(), conversation_id=conv.id, op="conversation_upsert",
        payload=doc, actor_id=actor_id)
```

### `services/message.py` — CQRS: `persist_inbound` (outbox), `relay_outbox` (→Firestore), `send_outbound` (Meta+Firestore), `apply_status` (doc Firestore), `list_messages` (fallback)

> **🔑 El mensaje NO se escribe en Postgres.** `persist_inbound`/`send_outbound` escriben (a) el `message_outbox` durable + denormalizados en la **TX Postgres** (atómico, idempotente por `id=mid`), y (b) el **doc Firestore** vía Admin SDK (directo en outbound, o a través de `relay_outbox` en inbound). La lectura primaria del hilo es el **cliente Firestore real-time** (`onSnapshot`); `list_messages` es solo un fallback server-side. El `payload` que se encola en el outbox **es el doc EXACTO** (mismo shape que `MessageItem`, snake_case) → el relay lo escribe sin transformar.

```python
async def persist_inbound(
    db, *, conversation: Conversation, mid: str, content: str | None,
    content_type: ContentType, sent_at: datetime, provider_payload: dict,
) -> bool:
    """Persiste un mensaje ENTRANTE en el control plane (TX Postgres) como op del outbox.
    IDEMPOTENTE por `mid` (= wamid; el `enqueue` hace ON CONFLICT (id) DO NOTHING): si ya
    estaba → no-op (devuelve False, el webhook NO incrementa unread). Si es nuevo: encola
    `message_create` (el doc a escribir en Firestore) + `conversation_upsert` (espejo del
    conversation doc) + actualiza unread_count/last_message_* en `conversation`. NO escribe
    Firestore acá (eso lo hace relay_outbox, fuera de la tx). NO toca crm (no MESSAGE_SENT — §1)."""
    now = utc_now()
    doc = {  # shape de conversations/{cid}/messages/{mid} (snake_case, = MessageItem)
        "id": mid, "conversation_id": conversation.id,
        "direction": MessageDirection.inbound.value, "sender_type": SenderType.contact.value,
        "sender_user_id": None, "bot_configuration_id": None,
        "content_type": content_type.value, "content": content,
        "external_id": mid, "external_status": None,
        "sent_at": sent_at, "delivered_at": None, "read_at": None,
        "failed_at": None, "failure_reason": None, "attachments": [],
        "provider_payload": provider_payload, "created_at": now,
    }
    inserted = await message_outbox_repository.enqueue(
        db, id=mid, conversation_id=conversation.id, op="message_create",
        payload=doc, actor_id=SYSTEM_USER_ID,
    )
    if not inserted:
        return False  # reenvío de Meta → ya procesado
    conversation.unread_count += 1
    conversation.last_message_at = sent_at
    conversation.last_message_preview = (content or "")[:255]
    conversation.updated_by = SYSTEM_USER_ID; conversation.updated_on = now
    # Espejo del conversation doc en Firestore (status/assignee/allowed_reader_ids/preview/unread).
    await conversation_service.enqueue_conversation_upsert(db, conversation, actor_id=SYSTEM_USER_ID)
    return True


async def relay_outbox(db, *, limit: int = 100) -> int:
    """RELAY: lee message_outbox pendientes y los escribe a Firestore con el Admin SDK.
    Idempotente por doc-id (`set(doc_id=mid)` = create-if-absent/overwrite). Marca `done`;
    reintenta por-fila vía attempts/last_error. Se invoca SÍNCRONO en el request (misma
    sesión: `await relay_outbox(db)` tras `process_inbound`/`send_outbound`, ANTES del 200).
    BackgroundTasks fue DESCARTADO (no proyectaba en Cloud Run). Un sweep/Cloud Task de filas
    `failed` (`relay_outbox_in_new_session`, sesión propia) queda como recuperación de infra.
    NUNCA pierde un mensaje (el outbox es durable; reprocesar un done no duplica)."""
    from app.core import firestore
    pending = await message_outbox_repository.list_pending(db, limit=limit)
    relayed = 0
    for row in pending:
        try:
            if row.op == "message_create":
                firestore.write_message_doc(row.conversation_id, row.payload)  # set(doc_id=mid)
            elif row.op == "conversation_upsert":
                firestore.upsert_conversation_doc(row.conversation_id, row.payload)
            elif row.op == "message_status":
                firestore.update_message_status(row.conversation_id, row.payload)
            await message_outbox_repository.mark_done(db, row.id)
            relayed += 1
        except Exception as exc:  # red / permisos Firestore → queda pending/failed, se reintenta
            await message_outbox_repository.mark_failed(db, row.id, error=str(exc))
            logger.warning("outbox relay failed", extra={"outbox_id": row.id, "op": row.op, "error": str(exc)})
    await db.flush()
    return relayed


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
    from app.core import firestore
    now = utc_now()
    mid = generate_uuid()  # el mid outbound (doc-id Firestore = id del outbox)
    doc = {
        "id": mid, "conversation_id": conv.id, "direction": MessageDirection.outbound.value,
        "sender_type": SenderType.advisor.value, "sender_user_id": actor_id,
        "bot_configuration_id": None, "content_type": ContentType.text.value,
        "content": payload.content, "external_id": None,
        "external_status": MessageExternalStatus.sent.value,  # provisional; se corrige abajo
        "sent_at": now, "delivered_at": None, "read_at": None,
        "failed_at": None, "failure_reason": None, "attachments": [],
        "provider_payload": None, "created_at": now,
    }
    # 1) TX Postgres: encolar el message_create (status=pending) + denorm + conversation_upsert. COMMIT-able.
    await message_outbox_repository.enqueue(
        db, id=mid, conversation_id=conv.id, op="message_create", payload=doc, actor_id=actor_id)
    conv.last_message_at = now
    conv.last_message_preview = payload.content[:255]
    conv.updated_by = actor_id; conv.updated_on = now
    await conversation_service.enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    # 2) Escribir el doc Firestore (status pending/sent) → el asesor lo ve INSTANTÁNEO vía su listener.
    firestore.write_message_doc(conv.id, doc)
    # 3) Enviar REAL contra Meta. Éxito → patch del doc {external_id, external_status:sent, sent_at}.
    #    Falla → patch {failed_at, failure_reason, external_status:failed}. 200 al cliente (reintento UI).
    ca = await channel_account_repository.get_by_id(db, conv.channel_account_id)
    try:
        creds = await channel_account_service.get_credentials(db, ca)
        result = await _meta_send_text(creds, to=<person primary identifier>, body=payload.content)
        doc["external_id"] = result["wamid"]
        doc["external_status"] = MessageExternalStatus.sent.value
    except Exception as exc:  # red / 4xx-5xx de Meta / credenciales
        doc["failed_at"] = now
        doc["failure_reason"] = str(exc)[:255]
        doc["external_status"] = MessageExternalStatus.failed.value
        logger.warning("outbound send failed", extra={"conversation_id": conv.id, "error": str(exc)})
    firestore.update_message_status(conv.id, doc)  # patch del doc Firestore (real-time)
    await db.flush()
    return SingleResponse(data=_doc_to_message_item(doc))  # 200 incluso si failed


async def apply_status(db, *, conversation_id: str | None, external_id: str, status: str, ts: datetime) -> None:
    """statuses[] del webhook → marca delivered_at/read_at/failed_at + external_status
    DIRECTO en el doc Firestore (real-time; NO toca Postgres — el status es best-effort).
    No-op si el mensaje no existe (status de un mensaje que no enviamos)."""
    from app.core import firestore
    # El status best-effort se aplica directo (sin outbox). Si conversation_id no viene en el
    # callback se resuelve por external_id (collection group query en Firestore; raro colisionar).
    field = {"delivered": "delivered_at", "read": "read_at", "failed": "failed_at"}.get(status)
    patch = {"external_status": status}
    if field is not None:
        patch[field] = ts
    firestore.update_message_status(conversation_id, {"external_id": external_id, **patch})


async def list_messages(
    db, conversation_id: str, query: QueryRequest, *, actor_id: str
) -> PaginatedResponse[MessageItem]:
    """FALLBACK server-side (SSR / cliente sin Firestore). Lee
    conversations/{cid}/messages del Admin SDK (orderBy created_at), pagina, hidrata
    sender_user (UserAuditInfo) con get_audit_info_map, mapea cada doc a MessageItem. El
    path PRIMARIO de lectura es el cliente Firestore real-time (onSnapshot); este endpoint
    existe para SSR y degradación."""
    from app.core import firestore
    docs, total = firestore.list_message_docs(conversation_id, skip=query.skip, limit=query.limit)
    sender_ids = [d["sender_user_id"] for d in docs if d.get("sender_user_id")]
    audit = await user_repository.get_audit_info_map(db, sender_ids)
    items = [_doc_to_message_item(d, sender_user=audit.get(d.get("sender_user_id"))) for d in docs]
    return PaginatedResponse(data=PaginatedData(items=items, total=total, skip=query.skip, limit=query.limit))
```

> **Outbound fallido (decisión §1)**: el mensaje se persiste **siempre** (en el outbox + doc Firestore, marcado `failed_at`/`failure_reason`/`external_status='failed'`); el endpoint devuelve **200** con el mensaje en estado fallido (la UI muestra "Falló el envío / Reintentar"), **NO** 502. El asesor ve el mensaje pendiente instantáneo (paso 2) y luego su transición a sent/failed (paso 3) por su listener. Reintento = mensaje nuevo (mid uuid nuevo). `MESSAGE_SEND_FAILED` se usa solo internamente (log), no como status HTTP.
> **`_meta_send_text`** (en `services/message.py` o un thin client `services/webhook_processor/whatsapp.py`): `POST https://graph.facebook.com/v<ver>/{phone_number_id}/messages` con `Authorization: Bearer {access_token}` y body `{messaging_product:"whatsapp", to, type:"text", text:{body}}`. Usa `httpx.AsyncClient`. El `to` es el identifier primario WhatsApp de la Person (resuelto vía `conversation.person_id` → identifier). Timeout corto (≈10 s).
> **`relay` inbound vs `directo` outbound**: el inbound encola en el outbox y el router invoca `relay_outbox(db)` **síncrono en el mismo request/sesión, antes del 200** (no BackgroundTasks — se descartó por no proyectar en Cloud Run) para escribir a Firestore. El outbound escribe el doc **inline** (pasos 2 y 3) para que el asesor vea su propio mensaje sin latencia; el outbox sigue siendo la fuente durable (si la escritura falla, el sweep/Cloud Task lo recupera). **Postgres manda; Firestore es proyección eventual** (latencia ms–seg). Audit/analítica de mensajes = export Firestore→BigQuery (nativo GCP), no Postgres.

### `services/webhook_processor/whatsapp.py` — verify firma + parse + orquestación

```python
import hashlib
import hmac

from app.modules.conversations.enums import AssigneeType, ContentType, MessageDirection, SenderType
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


async def process_inbound(db, *, payload: dict, channel_account: ChannelAccount) -> dict[str, str]:
    """Parse del payload de WhatsApp Cloud API: entry[].changes[].value.{messages[], statuses[],
    contacts[]}. Flujo SÍNCRONO. Texto primero (media diferida F4). Devuelve `bot_dispatches`
    ({conversation_id: mid}) de las conversaciones recién con inbound cuyo assignee_type=bot →
    el router las encola con cloud_tasks.enqueue_turn (auto-path del bot, ADR-012)."""
    bot_dispatches: dict[str, str] = {}
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
                # persist_inbound encola message_create (+ conversation_upsert) en el outbox;
                # IDEMPOTENTE por mid (= wamid). El relay SÍNCRONO (`relay_outbox(db)`, lo invoca
                # el router tras este process_inbound, misma sesión, antes del 200) lo escribe a
                # Firestore. Devuelve si insertó algo nuevo (False = reenvío deduplicado).
                inserted = await message_service.persist_inbound(
                    db, conversation=conv, mid=m["id"], content=content,
                    content_type=content_type, sent_at=_ts(m.get("timestamp")), provider_payload=m)
                # Auto-path del bot (ADR-012): si la conversación la atiende un bot y el inbound
                # fue nuevo, marca el turno a encolar (el router lo despacha vía Cloud Tasks).
                if inserted and conv.assignee_type == AssigneeType.bot.value:
                    bot_dispatches[conv.id] = m["id"]
            for s in value.get("statuses", []):
                # apply_status patchea el doc Firestore directo (best-effort; NO toca Postgres).
                await message_service.apply_status(
                    db, conversation_id=None, external_id=s["id"],
                    status=s["status"], ts=_ts(s.get("timestamp")))
    return bot_dispatches
```

> **Contacto desconocido (default §1)**: `PersonCreate(first_name = pushname.trim()[:80] o "Contacto", last_name = "(WhatsApp)", identifiers=[])`. `last_name` exige `min_length=1` (validador de `crm.PersonCreate`); el placeholder `"(WhatsApp)"` es editable por el asesor. `find_by_identifier_or_create` **ignora** `profile.identifiers` (construye el suyo con `(whatsapp, wa_id)` primario no verificado) → se pasa lista vacía.
> **Flujo síncrono (control plane + relay del read-model)**: la **TX Postgres** (verify firma + resolver Person + `find_or_create_open` + `enqueue` outbox + denorm + status) **y** la **escritura a Firestore** (relay del outbox, `await message_service.relay_outbox(db)`) ocurren **AMBAS antes del 200**, en el mismo request y la misma sesión (read-your-writes). **`BackgroundTasks` fue DESCARTADO**: en Cloud Run la sesión nueva del task no veía los rows del request (timing del commit de `get_db` + cpu-throttling) → el doc nunca llegaba a Firestore. La durabilidad la garantiza el outbox (si una fila queda `failed`, el sweep/Cloud Task `relay_outbox_in_new_session` reintenta; nunca se pierde un mensaje). Tras el relay, las conversaciones assignee=bot se encolan vía Cloud Tasks (auto-path del bot, ADR-012). **Cuándo migrar a cola para el procesamiento**: cuando `bots` (#6) agregue auto-reply lento (LLM) que no quepa en el request → 200 inmediato + cola (Cloud Tasks) + Cloud Run `--no-cpu-throttling --min-instances 1`.

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

## 7-bis. `app/core/firestore.py` — Firebase Admin SDK (data plane) — ADR-011

Cross-cutting reusable (como `secrets.py`). Inicializa el **Firebase Admin SDK** vía **ADC** (la SA de Cloud Run, sin key file), expone el cliente Firestore por entorno (`get_db`), mintea **Custom Tokens** (firma vía `signBlob`), y escribe/patchea los docs del read-model. **Lazy import** de `firebase_admin` (no al import del módulo) → el smoke (sqlite, sin GCP) NO rompe; el path de test usa fallback/mock/emulador.

```python
"""
Firebase Admin SDK bootstrap (ADR-011) — el lado SERVIDOR del read-model Firestore.
- Init LAZY vía ADC (Application Default Credentials): en Cloud Run = la SA del servicio
  (medisage-sa[-qa]); local/dev = ADC de gcloud o key file. NUNCA un key file en Secret
  Manager (ADC es más robusto). La SA necesita roles/datastore.user (Firestore RW) +
  roles/iam.serviceAccountTokenCreator sobre sí misma (firmar custom tokens vía signBlob).
- get_db(): cliente Firestore de la database NOMBRADA del entorno (medisage-qa / medisage),
  elegida por ENV_NAME (espeja el patrón de Cloud SQL).
- mint_custom_token(uid, claims): create_custom_token(uid, developer_claims=claims).
- write_message_doc / upsert_conversation_doc / update_message_status: escriben los docs
  del read-model (set por doc-id = idempotente). El Admin SDK BYPASSA las Security Rules
  (las rules solo gobiernan al cliente Web).
- firebase_admin se importa LAZY (no al import del módulo) → smoke sin GCP no rompe.
"""

from __future__ import annotations

from app.core.config import get_settings

_app = None   # firebase_admin.App lazy
_db = None    # firestore client lazy

# Database nombrada por entorno (espeja Cloud SQL). dev → la (default) o el emulador.
_DB_BY_ENV = {"prod": "medisage", "qa": "medisage-qa"}


def _get_app():
    global _app
    if _app is None:
        import firebase_admin  # lazy: solo se carga en Cloud Run / con ADC presente
        from firebase_admin import credentials
        # ADC: en Cloud Run resuelve la SA del servicio; local usa gcloud ADC / key file.
        _app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            {"projectId": get_settings().GCP_PROJECT_ID},
        )
    return _app


def get_db():
    """Cliente Firestore de la database nombrada del entorno."""
    global _db
    if _db is None:
        from firebase_admin import firestore
        env = get_settings().ENV_NAME
        database_id = _DB_BY_ENV.get(env)  # None → (default) DB
        _db = firestore.client(app=_get_app(), database_id=database_id)
    return _db


def mint_custom_token(uid: str, claims: dict) -> str:
    """Firebase Custom Token (JWT firmado vía signBlob por la SA). Lo intercambia el browser
    por un ID token (1 h) con signInWithCustomToken. `claims` van como developer_claims y
    quedan en request.auth.token (los leen las Security Rules)."""
    from firebase_admin import auth
    token = auth.create_custom_token(uid, developer_claims=claims, app=_get_app())
    return token.decode("utf-8") if isinstance(token, bytes) else token


def revoke_tokens(uid: str) -> None:
    """Logout / cambio de permisos → invalida los refresh tokens Firebase del uid."""
    from firebase_admin import auth
    auth.revoke_refresh_tokens(uid, app=_get_app())


def write_message_doc(conversation_id: str, doc: dict) -> None:
    """conversations/{cid}/messages/{mid} ← set(doc, merge=False). doc-id = doc['id'] (mid)
    → create-if-absent idempotente (reprocesar el outbox no duplica)."""
    db = get_db()
    db.collection("conversations").document(conversation_id) \
      .collection("messages").document(doc["id"]).set(doc)


def upsert_conversation_doc(conversation_id: str, doc: dict) -> None:
    """conversations/{cid} ← set(doc, merge=True). Espejo liviano del Conversation de
    Postgres (status/assignee/allowed_reader_ids/preview/unread). Idempotente por overwrite."""
    get_db().collection("conversations").document(conversation_id).set(doc, merge=True)


def update_message_status(conversation_id: str | None, patch: dict) -> None:
    """Patch del doc de un mensaje (delivered/read/failed + external_status). Si conversation_id
    viene → update directo por (cid, mid); si NO (status callback sin cid) → collection group
    query por external_id para ubicar el doc."""
    db = get_db()
    if conversation_id is not None:
        db.collection("conversations").document(conversation_id) \
          .collection("messages").document(patch.get("id") or _by_external(patch)).set(patch, merge=True)
        return
    # Sin cid: collection group query por external_id (raro; el wamid es único en Meta).
    from firebase_admin import firestore
    q = db.collection_group("messages").where(
        filter=firestore.FieldFilter("external_id", "==", patch["external_id"])
    ).limit(1).stream()
    for snap in q:
        snap.reference.set(patch, merge=True)


def list_message_docs(conversation_id: str, *, skip: int, limit: int) -> tuple[list[dict], int]:
    """Fallback server-side (SSR / sin Firestore en el cliente): lee
    conversations/{cid}/messages orderBy created_at, pagina. Devuelve (docs, total)."""
    db = get_db()
    base = db.collection("conversations").document(conversation_id).collection("messages")
    total = base.count().get()[0][0].value  # aggregation query
    docs = [s.to_dict() for s in base.order_by("created_at").offset(skip).limit(limit).stream()]
    return docs, total
```

> **Dependencia nueva**: `firebase-admin` (pin en `pyproject.toml`, ej. `firebase-admin>=6.5,<7`). **ADC, no key file**: en Cloud Run la SA `medisage-sa[-qa]` provee las credenciales; agregar a esa SA `roles/datastore.user` (Firestore RW) + `roles/iam.serviceAccountTokenCreator` **sobre sí misma** (para firmar los custom tokens vía `signBlob` sin key file). Local/dev: ADC de `gcloud auth application-default login` o un key file fuera de Secret Manager. **El proyecto Firebase se linkea al GCP project `proyecto-ifc-497317`** (un solo proyecto; las databases nombradas separan qa/prod). **Lazy**: `firebase_admin` se importa dentro de las funciones → el boot local/smoke sin GCP no rompe (el smoke nunca llama Firestore: el path de test mockea estas funciones o usa el emulador). **El Admin SDK bypassa las Security Rules** (esas gobiernan solo al cliente Web; el backend escribe con privilegios plenos).

---

## 7-ter. Firestore data model + `firestore.rules` (read-model real-time) — ADR-011

### Colecciones / docs (Native mode, snake_case = contrato API)

```
conversations/{cid}                         # cid = UUID del Conversation de Postgres (clave de join)
  {
    status,                 # 'open' | 'closed'
    assignee_user_id,       # string | null
    allowed_reader_ids,     # [uid, ...]  ← gobierna las Security Rules (assignee + supervisores)
    channel_account_id,     # string
    person_name,            # denormalizado (para el inbox live)
    person_id,              # string | null
    last_message_at,        # timestamp | null
    last_message_preview,   # string | null
    unread_count,           # int
    updated_at,             # timestamp
  }

conversations/{cid}/messages/{mid}          # mid = wamid (inbound) | uuid (outbound) → idempotencia natural
  {
    direction, sender_type, sender_user_id, bot_configuration_id,
    content_type, content, external_id, external_status,
    sent_at, delivered_at, read_at, failed_at, failure_reason,
    attachments: [ {type, url, mime, ...} ],   # vacío hasta F4 (texto primero); url = GCS firmada en F4
    provider_payload, created_at,
  }
```

> **`cid` = el UUID del `Conversation` de Postgres** (NO un id Firestore autogenerado) → la fila Postgres y el doc Firestore comparten clave (join determinístico). **`mid` = `wamid`/`uuid`** = doc-id → `set(doc_id=mid)` es create-if-absent (idempotencia natural ante el reenvío de Meta o el reprocesamiento del outbox). Ambas colecciones las escribe **SOLO el backend** (Admin SDK); el cliente jamás escribe. El shape es **snake_case a propósito** (alineado con `MessageItem`/el envelope de la API) → el browser lee el doc tal cual y el fallback `list_messages` devuelve el mismo shape. Los `attachments[]` viven embebidos en el doc del mensaje (no hay sub-colección de adjuntos — reemplaza la tabla `message_attachment`).

> **Edición / región (decisión §1 del brief)**: **Native mode (Standard edition)** — REQUERIDO para los listeners real-time del Web SDK + Security Rules. **NO** Datastore mode ni Enterprise/MongoDB-compat. Location `us-central1` (colocar con Cloud SQL/Run; es permanente). **Una database Firestore por entorno** (named DBs): `medisage-qa` y `medisage` (prod), espejando el patrón de Cloud SQL; el backend elige por `ENV_NAME` (ver `_DB_BY_ENV` en `firestore.py`).

### `firestore.rules` (versionado en el repo, desplegado por CI)

Espeja el RBAC del template: el cliente solo LEE lo que su token autoriza; **NUNCA escribe** (`allow write: if false` — solo el Admin SDK, que bypassa las rules). El `scope`/`can_read_all`/`uid` salen de los `developer_claims` del Custom Token minteado por el backend (que ya gateó por permiso). La autorización por hilo = `can_read_all` (supervisor con `CONVERSATIONS_READ`) **o** `uid ∈ allowed_reader_ids` (asignado).

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /conversations/{cid} {
      allow read:  if request.auth.token.scope == 'conversations'
                   && (request.auth.token.can_read_all == true
                       || request.auth.uid in resource.data.allowed_reader_ids);
      allow write: if false;                  // clientes NUNCA escriben
      match /messages/{mid} {
        allow read:  if request.auth.token.scope == 'conversations'
                     && (request.auth.token.can_read_all == true
                         || request.auth.uid in get(/databases/$(database)/documents/conversations/$(cid)).data.allowed_reader_ids);
        allow write: if false;                // solo Admin SDK (bypassa rules)
      }
    }
  }
}
```

> **`allowed_reader_ids`** = `[assignee_user_id]` + `[admins/supervisores con CONVERSATIONS_READ]` — lo mantiene el backend vía el outbox (`conversation_upsert`) cada vez que cambia la asignación/estado (`enqueue_conversation_upsert`, §6). El sub-doc de mensaje hace `get(...conversations/$(cid))` para reusar el `allowed_reader_ids` del padre (una lectura extra por regla; aceptable para el caudal del inbox). **Clientes read-only**: TODO write (enviar, tomar, liberar, cerrar) va browser → Next server → backend → Meta + Firestore (Admin SDK). Se preserva el principio del template (el browser solo LEE el stream que está autorizado a ver; el backend muta).

> **Despliegue (CI)**: `firestore.rules` se versiona en el repo (raíz o `backend/firestore.rules`) y se despliega con `firebase deploy --only firestore:rules --project proyecto-ifc-497317` (o `gcloud firestore` equivalente) por entorno, como un step del pipeline tras provisionar la database. La provisión de la DB Native mode (`gcloud firestore databases create --database=medisage-qa --location=us-central1 --type=firestore-native`) + las rules base van en **F1** (junto al bootstrap del Admin SDK); la lógica de `allowed_reader_ids` se activa en **F2** (cuando existen las conversaciones). Indexes: las queries del MVP (`messages` orderBy `created_at`; collection group por `external_id`) usan índices de campo único / automáticos; un `firestore.indexes.json` se agrega solo si una query compuesta lo exige (anotado para F2).

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

### 8.5 Helper aditivo a `admin`: `list_user_ids_with_permission` (para `allowed_reader_ids`) — CAMBIO #4

`enqueue_conversation_upsert` (§6) y `realtime.mint_token` (§9) necesitan resolver el conjunto de **supervisores con `CONVERSATIONS_READ`** (los que pueden leer cualquier hilo). Se agrega un helper aditivo a `admin.user_repository` (molde `staff.list_active_by_role`/`has_role` de §F3 de staff):

```python
# admin/repositories/user.py — aditivo, backward-compatible
async def list_user_ids_with_permission(self, db, permission_code: str) -> list[str]:
    """user_ids ACTIVOS con un permiso dado (vía sus roles). Para computar allowed_reader_ids
    del read-model Firestore (supervisores que leen toda la bandeja)."""
    # JOIN user → user_role → role_permission → permission WHERE permission.code = ? AND user.active
    ...
```

Lectura aditiva (los callers existentes de `admin` no cambian). **Caveat**: el resultado se cachea/recomputa al encolar el `conversation_upsert` (no per-request del cliente). Cuando un admin pierde/gana `CONVERSATIONS_READ`, los hilos reflejan el nuevo `allowed_reader_ids` en su próximo `conversation_upsert` (al siguiente mensaje/handoff); un re-sweep opcional (recomputar todos los docs abiertos) queda anotado para hardening. Esto es consistente con el modelo de permisos del template (los cambios surten efecto al siguiente refresh).

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
| POST | `/realtime/token` | `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` | mintea el Firebase Custom Token → `SingleResponse[RealtimeTokenResponse]` (`{token, firebase_config?}`) |
| POST | `/list` | `CONVERSATIONS_READ` | inbox global. `QueryRequest` + query params deep-link → `PaginatedResponse[ConversationListItem]` |
| GET | `/{id}` | `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` | `SingleResponse[ConversationDetail]` (+ `assignment_history`). El service scopea: un titular solo de `MY_CONVERSATIONS_READ` abre únicamente sus hilos (ajenos → 404) |
| POST | `/{id}/messages/list` | `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` **o** `MESSAGES_READ` | **FALLBACK** lectura del hilo (lee Firestore vía Admin SDK server-side). `QueryRequest` → `PaginatedResponse[MessageItem]`. El path PRIMARIO es el cliente Firestore real-time (`onSnapshot`). Mismo gate que el token real-time (`MESSAGES_READ` por compat) |
| POST | `/{id}/messages` | `MESSAGES_SEND` | `MessageSendRequest` → `SingleResponse[MessageItem]` (envío real; 200 aun si falló) |
| POST | `/{id}/take` | `CONVERSATIONS_TAKE` | `TakeConversationRequest` → `SingleResponse[ConversationDetail]` |
| POST | `/{id}/release` | `CONVERSATIONS_RELEASE` | `ReleaseConversationRequest` → `SingleResponse[ConversationDetail]` |
| POST | `/{id}/close` | `CONVERSATIONS_CLOSE` | `SingleResponse[ConversationDetail]` |
| POST | `/{id}/reopen` | `CONVERSATIONS_TAKE` | `SingleResponse[ConversationDetail]` (valida no-otra-open) |
| POST | `/{id}/mark-read` | `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` | `SingleResponse[ConversationDetail]` (todo titular del token de lectura puede marcar leída una conversación que ve) |
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
    result = await message_service.send_outbound(db, conversation_id, payload, actor_id=actor.id)
    await message_service.relay_outbox(db)   # relay SÍNCRONO (misma sesión, antes del 200)
    return result

@router.post("/{conversation_id}/take", response_model=SingleResponse[ConversationDetail],
             dependencies=[Depends(RequirePermission("CONVERSATIONS_TAKE"))])
async def take_conversation(conversation_id: ConvIdPath, payload: TakeConversationRequest,
                            db: DBSession, actor: CurrentAuth) -> SingleResponse[ConversationDetail]:
    result = await conversation_service.take(db, conversation_id, actor_id=actor.id, reason=payload.reason)
    await message_service.relay_outbox(db)   # cada mutación encola conversation_upsert → relay inline
    return result
```

> **Nota de prefijos**: el aggregator `routers/__init__.py` declara `prefix="/conversations"`. Para evitar `/conversations/conversations`, los sub-routers `channel_account_router`/`conversation_router` usan prefijos relativos (`/channel-accounts`, y `""` para las rutas raíz como `/list`, `/{id}`). Es exactamente el mismo encaje que crm (`crm/routers/__init__.py` con `prefix="/crm"` + `person_router` con `prefix="/persons"`). Verificar al implementar que `POST /api/v1/conversations/list` resuelve (no `/conversations/conversations/list`). **`/realtime/token` se declara en su propio sub-router y se incluye ANTES de `conversation_router`** (cuyo `/{id}` capturaría `/realtime` si fuera al revés).

### 9.1-bis Router de real-time token — `routers/realtime.py` (mint Custom Token)

```python
# routers/realtime.py
from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentAuth, DBSession
from app.core.permissions import RequireAnyPermission  # gate por CUALQUIERA de los dos permisos
from app.modules.conversations.schemas.realtime import RealtimeTokenResponse
from app.modules.conversations.services import realtime as realtime_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/realtime", tags=["conversations"])


@router.post("/token", response_model=SingleResponse[RealtimeTokenResponse],
             dependencies=[Depends(RequireAnyPermission("CONVERSATIONS_READ", "MY_CONVERSATIONS_READ"))])
async def realtime_token(db: DBSession, actor: CurrentAuth) -> SingleResponse[RealtimeTokenResponse]:
    """Mintea el Firebase Custom Token para que el browser abra listeners read-only. El
    RBAC del template es la fuente de verdad: el endpoint exige CONVERSATIONS_READ o
    MY_CONVERSATIONS_READ; los claims (scope/is_advisor/can_read_all) salen de los permisos
    del actor."""
    return await realtime_service.mint_token(db, actor=actor)
```

```python
# services/realtime.py
from app.core import firestore


async def mint_token(db, *, actor) -> SingleResponse[RealtimeTokenResponse]:
    """Custom Token con developer_claims que ESPEJAN el RBAC (los leen las Security Rules):
    - scope='conversations' (namespacing del token; las rules lo exigen).
    - can_read_all = el actor tiene CONVERSATIONS_READ (supervisor / bandeja global) → puede
      leer cualquier hilo. Si solo tiene MY_CONVERSATIONS_READ → can_read_all=False → solo
      sus hilos (uid ∈ allowed_reader_ids).
    - is_advisor = bandera de conveniencia para la UI.
    El uid del token = actor.id (el mismo id que va en allowed_reader_ids / assignee_user_id)."""
    can_read_all = "CONVERSATIONS_READ" in actor.permissions
    claims = {
        "scope": "conversations",
        "can_read_all": can_read_all,
        "is_advisor": "MY_CONVERSATIONS_READ" in actor.permissions,
    }
    token = firestore.mint_custom_token(actor.id, claims)
    return SingleResponse(data=RealtimeTokenResponse(token=token, firebase_config=_public_firebase_config()))
```

> **Por qué `can_read_all = (CONVERSATIONS_READ in permissions)`**: `CONVERSATIONS_READ` es el permiso de la bandeja **global** (supervisor/admin) → ese rol lee cualquier hilo (`can_read_all=true` en el token → la regla lo deja pasar sin chequear `allowed_reader_ids`). El asesor común tiene `MY_CONVERSATIONS_READ` pero NO `CONVERSATIONS_READ` → `can_read_all=false` → solo lee los hilos donde su `uid` está en `allowed_reader_ids` (los asignados a él + los que tomó). Es **exactamente el mismo gate** que ya aplica el backend al `POST /list` (global) vs `POST /me/conversations/list` (propios), trasladado a las Security Rules vía el claim. El `uid` del Custom Token = `actor.id` = el id que el backend pone en `assignee_user_id`/`allowed_reader_ids`. **Revocación**: en logout / cambio de permisos, el backend llama `firestore.revoke_tokens(actor.id)` (invalida el refresh Firebase; el cliente pierde el acceso al refrescar). `RequireAnyPermission` es el dep de "cualquiera de N permisos" (si el template no lo trae, se agrega como helper aditivo a `app/core/permissions.py`, molde de `RequirePermission`).

### 9.2 Webhooks top-level — `app/routers/webhooks.py` (sin JWT)

| Método | Ruta | Auth | Propósito |
|---|---|---|---|
| GET | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT; compara `hub.verify_token` con `ChannelAccount.webhook_verify_token` | Meta verification challenge → devuelve `hub.challenge` (200, **text/plain**) o 403 |
| POST | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT; valida `X-Hub-Signature-256` (HMAC SHA256 del **body raw** con `app_secret`) | inbound messages + status callbacks → 200 |

```python
# app/routers/webhooks.py
from fastapi import APIRouter, Query, Request, Response, status

from app.core import cloud_tasks
from app.core.dependencies import DBSession
from app.core.exceptions import ForbiddenException, NotFoundException
from app.modules.conversations.repositories.channel_account import channel_account_repository
from app.modules.conversations.services import channel_account as channel_account_service
from app.modules.conversations.services import message as message_service
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
async def inbound_whatsapp(
    channel_account_id: str, request: Request, db: DBSession
) -> dict[str, bool]:
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
    payload = json.loads(raw or b"{}")
    # TX Postgres (control plane) → relay a Firestore, AMBOS SÍNCRONOS en el request y la MISMA
    # sesión, ANTES del 200. El relay lee los outbox rows recién flushed (read-your-writes) y los
    # proyecta con el Admin SDK. BackgroundTasks fue DESCARTADO: en Cloud Run la sesión nueva del
    # task no veía los rows del request (timing del commit de get_db + cpu-throttling) → el doc
    # nunca llegaba a Firestore. El sweep/Cloud Task de filas `failed` queda como entry-point de
    # infra (relay_outbox_in_new_session). El outbox es durable: nunca se pierde un mensaje.
    bot_dispatches = await wa.process_inbound(db, payload=payload, channel_account=ca)
    await message_service.relay_outbox(db)
    # Auto-path del bot (ADR-012): tras proyectar el inbound, encola UN turno por conversación
    # assignee=bot (best-effort; no rompe el 200 a Meta; NO-OP en dev / sin cola).
    for conv_id, mid in bot_dispatches.items():
        await cloud_tasks.enqueue_turn(conversation_id=conv_id, input_message_id=mid)
    return {"success": True}                           # 200 tras la TX + el relay síncrono
```

> **Sin JWT**: el router top-level no usa `RequirePermission`/`CurrentAuth` — la autenticación es la firma HMAC (POST) / el verify token (GET), no el RBAC del template. **`raw_body`**: la firma de Meta es sobre los bytes exactos del body → `await request.body()` ANTES de parsear JSON (re-serializar cambiaría los bytes y rompería la firma). **404 antes de firma**: si la cuenta no existe/está inactiva → 404 sin tocar credenciales. **Error inesperado en `process_inbound`** → 500 (Meta reintenta; la idempotencia por `message_outbox.id` (= wamid) + el doc-id Firestore evitan duplicados). **GET verify** devuelve el `hub.challenge` crudo (text/plain), NO un envelope. `telegram` diferido (URL futura `/webhooks/telegram/{channel_account_id}` con `X-Telegram-Bot-Api-Secret-Token`).
> **Relay SÍNCRONO antes del 200 (CQRS)**: la TX de control plane (Postgres) **y** la proyección a Firestore (data plane) corren AMBAS síncronas en el request, con la MISMA sesión, ANTES del 200: el router hace `await message_service.relay_outbox(db)` justo después de `process_inbound`/`send_outbound` (read-your-writes en la tx). **`BackgroundTasks` fue DESCARTADO**: en Cloud Run la sesión nueva del task no veía los rows del request (timing del commit de `get_db` + cpu-throttling) → el doc nunca llegaba a Firestore (cazado por el QA E2E). El outbox sigue dando durabilidad + idempotencia: si una fila queda `failed`, `relay_outbox_in_new_session` (thin wrapper que abre su propia `AsyncSession`) la reprocesa desde un sweep periódico / Cloud Task — **nunca se pierde un mensaje** (esa es la razón de ser del outbox).

---

## 10. Códigos de error (detalle ES + code EN + HTTP)

| code (EN) | HTTP | detail (ES) | Dónde |
|---|---|---|---|
| `CHANNEL_ACCOUNT_NOT_FOUND` | 404 | "Cuenta de canal no encontrada" | channel_account get/update/delete; webhook router |
| `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` | 409 | "Ya existe una cuenta de canal '{type}' con el identificador '{ext}'" | channel_account.create/update (guard unicidad) |
| `CHANNEL_CREDENTIALS_MISSING` | 400 | "No se pudo resolver el secreto del canal" | `get_credentials` / `secrets.resolve` vía `BadRequestException` (el template no tiene excepción de dominio 500). Server-side (F2/F3): NO se surface directo — en outbound NO se levanta (mensaje persiste fallido); en webhook la firma decide 403/200 |
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

Migraciones **manuales y numeradas**. La última aplicada es `0014_crm_customer_lifecycle`; `conversations` encadena desde ahí. UNIQUE parciales con `WHERE ...` (Postgres) — el smoke no las corre (usa `create_all` sobre los modelos, donde el `sqlite_where` reproduce el índice). JSONB en la columna `message_outbox.payload`. **El smoke `create_all` NO corre la migración** (JSONB / ALTER ADD FK son Postgres-only) → la migración se valida vía QA E2E sobre Postgres (reuse del patrón crm `0013`). **El stream de mensajes NO tiene migración Alembic** (vive en Firestore, ADR-011): su provisión (DB Native mode + rules) es infra/CI (§7-ter).

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

### `0016_conv_threads.py` (F2 — conversation + message_outbox + conversation_assignment_log + FK aditiva) · revid `0016_conv_threads` (17 chars ✓)

> **🔑 NO crea `message` ni `message_attachment`** (ya no son tablas Postgres — el stream vive en Firestore, ADR-011). Crea: `conversation` (control plane) + **`message_outbox`** (cola transaccional) + `conversation_assignment_log` + la FK aditiva `lead_activity→conversation`. La idempotencia que antes daba el UNIQUE parcial `(conversation_id, external_id)` de `message` ahora la da el **PK UNIQUE de `message_outbox.id`** (= mid) + el doc-id en Firestore.

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

    # ── message_outbox (A·T, SIN deleted_at — cola transaccional Postgres→Firestore) ─
    # NB: id = el `mid` (wamid inbound / uuid outbound) → varchar(255) (el wamid de Meta es
    # más largo que un uuid; el modelo NO hereda PrimaryKeyMixin → el id se crea a 255
    # directo, no se amplía). PK UNIQUE = idempotencia (ON CONFLICT (id) DO NOTHING).
    # NO se crean tablas message/message_attachment (el stream vive en Firestore, ADR-011).
    op.create_table(
        "message_outbox",
        sa.Column("id", sa.String(length=255), primary_key=True),   # = mid (wamid/uuid)
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("op", sa.String(length=40), nullable=False),       # message_create | message_status | conversation_upsert
        sa.Column("payload", postgresql.JSONB(), nullable=False),    # el doc a escribir en Firestore
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("processed_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_message_outbox_conversation_id", "message_outbox", ["conversation_id"])
    op.create_index("ix_message_outbox_status_created", "message_outbox", ["status", "created_on"])

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
    op.drop_index("ix_message_outbox_status_created", table_name="message_outbox")
    op.drop_index("ix_message_outbox_conversation_id", table_name="message_outbox")
    op.drop_table("message_outbox")
    op.drop_index("uq_conversation_person_channel_open", table_name="conversation")
    op.drop_index("ix_conversation_bot_configuration_id", table_name="conversation")
    op.drop_index("ix_conversation_assignee_user_id", table_name="conversation")
    op.drop_index("ix_conversation_person_id", table_name="conversation")
    op.drop_index("ix_conversation_channel_account_id", table_name="conversation")
    op.drop_table("conversation")
```

**Cadena de revids** (todos ≤32): `0014_crm_customer_lifecycle` (27) → `0015_conv_channel_account` (25) → `0016_conv_threads` (17). F0, F3 y F4 no llevan migración (F0 = solo seed/skeleton; F3 = las tablas ya existen; F4 = el doc Firestore del mensaje YA lleva `attachments[]`, solo se procesa media a GCS — NO hay tabla nueva). **Provisión de Firestore** (DB Native mode qa/prod + `firestore.rules` + roles IAM) NO es una migración Alembic — es un step de infra/CI (F1; ver §7-ter y los checklists).

> **Nota dialect-agnóstica (modelos vs migración)**: los **modelos** declaran el índice parcial con `postgresql_where + sqlite_where` (para que el smoke `create_all` lo reproduzca en sqlite); la **migración** escribe solo `postgresql_where` (la migración solo corre en Postgres). Es el patrón real shipped en crm (`crm/models/person_contact_identifier.py` usa ambos; `alembic/versions/0011_crm_person.py` usa solo `postgresql_where`).

---

## 13. Checklist de implementación (mapeado a fases F0–F3 + F4 diferida)

### F0 — Prep (sin migración; solo seed + skeleton)
- [ ] Agregar los 12 permisos `CONVERSATIONS` a `app/core/seed.py:SEED_PERMISSIONS` (ya canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md); no redefinir).
- [ ] Verificar que `_seed_role` aplique el subset `ASESOR` (los códigos `CONVERSATIONS_*`/`MESSAGES_*`/`MY_CONVERSATIONS_READ`/`MENU-CONVERSATIONS`) — el filtro por código los toma al existir el permiso (`DOCTOR` sin perms en conversations).
- [ ] Crear el skeleton `backend/app/modules/conversations/{enums,models,schemas,repositories,services,routers}/` (con `enums.py` completo + docstrings inertes). NO registrar en `app/modules/__init__.py` ni `main.py` todavía (lo cablea F1).
- [ ] (Frontend F0) nav grupo "Conversaciones" (`MENU-CONVERSATIONS`) + `endpoints.ts` (bloque conversations) + `types/conversations.types.ts` (espejo completo, inerte) — ver [`frontend.md`](frontend.md).
- [ ] Smoke: login admin → el JWT contiene los 12 permisos CONVERSATIONS.

### F1 — ChannelAccount + secret_resolver + Firebase Admin bootstrap (migración `0015_conv_channel_account`)
- [ ] `models/channel_account.py` (UNIQUE parcial dialect-agnóstico) + migración `0015_conv_channel_account` (`down_revision="0014_crm_customer_lifecycle"`).
- [ ] `schemas/channel_account.py` (`Create/Update/Item/Detail/Option`; `Detail` NUNCA expone el secreto, expone `secret_name` + flags `credentials_configured`/`has_verify_token`).
- [ ] `repositories/channel_account.py` (`ALLOWED_FIELDS` solo columnas reales, `get_by_external_id`, `list_active`).
- [ ] `services/channel_account.py` (CRUD + guard `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` + `get_credentials`).
- [ ] **`app/core/secrets.py`** (SDK Secret Manager async + cache TTL + fallback env, lazy init) + Settings nuevos (`GCP_PROJECT_ID`, `WHATSAPP_*`) + dep `google-cloud-secret-manager` en `pyproject.toml`.
- [ ] **`app/core/firestore.py`** (Firebase Admin SDK: init lazy ADC + `get_db` por env + `mint_custom_token` + doc writers) + dep `firebase-admin` en `pyproject.toml` (import lazy → boot/smoke sin GCP no rompe).
- [ ] **Provisionar Firestore** (infra/CI, NO Alembic): detectar/crear la DB **Native mode** `medisage-qa` y `medisage` (`gcloud firestore databases create --location=us-central1 --type=firestore-native`) + desplegar `firestore.rules` base (`firebase deploy --only firestore:rules`). Linkear el proyecto Firebase al GCP `proyecto-ifc-497317`.
- [ ] **Roles IAM de la SA** `medisage-sa[-qa]`: `roles/datastore.user` (Firestore RW) + `roles/iam.serviceAccountTokenCreator` sobre sí misma (firmar custom tokens).
- [ ] (Opcional en F1, sino F2) `routers/realtime.py` + `services/realtime.py` + `schemas/realtime.py` (`POST /realtime/token`, gate `CONVERSATIONS_READ` o `MY_CONVERSATIONS_READ`).
- [ ] Registrar `conversations` en `app/modules/__init__.py` + aggregator router (`/channel-accounts/*`) en `main.py`.
- [ ] `routers/channel_account.py` (CRUD + `/active` antes de `/{id}`).
- [ ] (Frontend F1) `/conversaciones/canales` (DataTable + drawer; secreto = "configurado/sin configurar") — ver [`ui.md`](ui.md).
- [ ] Test: crear ChannelAccount; duplicado `(channel_type, external_identifier)` vivo → `409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN`; soft-delete → se puede recrear; `Detail` no trae el secreto; `get_credentials` con `ENV_NAME=dev` toma el fallback env (no llama Secret Manager); el smoke (sin GCP) NO inicializa `firebase_admin` (import lazy / mock).

### F2 — Inbound pipe: control-plane + outbox + relay + Firestore data-plane (migración `0016_conv_threads`)
- [ ] `models/conversation.py` (UNIQUE parcial 1-open) + **`models/message_outbox.py`** (`id`=mid varchar(255) PK·UNIQUE, `op`/`payload` JSONB-variant/`status`/`attempts`/`last_error`, índice `(status, created_on)`; **NO** `message`/`message_attachment`) + `conversation_assignment_log.py` + migración `0016_conv_threads` (`down_revision="0015_conv_channel_account"`) **con la FK aditiva** `lead_activity.related_conversation_id → conversation.id`.
- [ ] `schemas/conversation.py` (`ConversationListItem`/`ConversationDetail`/`ConversationAssignmentLogItem`/Take/Release) + `schemas/message.py` (`MessageItem`/`MessageAttachmentItem`/`MessageSendRequest` — contrato API + shape del doc Firestore, snake_case).
- [ ] `repositories/{conversation,message_outbox,conversation_assignment_log}.py` (`get_open`, `has_other_open`, `list_inbox` con extra_filters; `message_outbox.enqueue` ON CONFLICT DO NOTHING/`list_pending`/`mark_done`/`mark_failed`; `get_current_open`/`list_for_conversation`) + batch maps de denorm.
- [ ] `app/routers/__init__.py` + `app/routers/webhooks.py` (GET verify + POST inbound con firma + relay SÍNCRONO `await relay_outbox(db)` antes del 200 + dispatch de bot vía Cloud Tasks) registrado en `main.py`.
- [ ] `services/webhook_processor/whatsapp.py` (`verify_signature` HMAC, `process_inbound` parse + `find_or_create_open` + `persist_inbound` + `apply_status`).
- [ ] `services/conversation.py` (`find_or_create_open` con auto-asignación vía `crm.lead_assignment_repository.advisor_map` + fallback unassigned + `enqueue_conversation_upsert`) + `services/message.py` (`persist_inbound` outbox+denorm, `relay_outbox` →Firestore, `apply_status` doc Firestore, `list_messages` fallback Firestore).
- [ ] **`app/core/firestore.py`** writers en uso (`write_message_doc`/`upsert_conversation_doc`/`update_message_status`/`list_message_docs`) + `firestore.rules` con la lógica de `allowed_reader_ids` desplegada (qa/prod).
- [ ] `services/realtime.py` + `routers/realtime.py` + `schemas/realtime.py` (si no se hizo en F1) — `POST /realtime/token` con claims scope/is_advisor/can_read_all.
- [ ] **crm hardening**: advisory lock en `find_by_identifier_or_create` (dialect-guard postgresql; sqlite no-op) + helper aditivo `admin.user_repository.list_user_ids_with_permission` (para `allowed_reader_ids`).
- [ ] `routers/conversation.py` (`/list`, `/{id}`, `/{id}/messages/list` fallback) + `routers/me.py` — solo recibir/ver (read).
- [ ] (Frontend F2) inbox 2-paneles; **thread con `onSnapshot` real-time** (read-only) + `getRealtimeToken` action + `lib/firebase/client.ts`; list por polling Postgres — ver [`ui.md`](ui.md).
- [ ] Test: webhook con firma válida crea Person (vía crm) + Conversation auto-asignada al dueño del lead (o unassigned) + outbox `message_create` encolado (unread_count=1) + doc Firestore escrito por el relay; reenvío del mismo `mid` (wamid) → `ON CONFLICT DO NOTHING` no-op (unread NO incrementa, doc-id idempotente); firma inválida → `403 WEBHOOK_SIGNATURE_INVALID`; GET verify con token correcto devuelve el challenge; cuenta inexistente → 404; `statuses[]` patchea el doc Firestore; `POST /realtime/token` con `CONVERSATIONS_READ` → token con `can_read_all=true`, con solo `MY_CONVERSATIONS_READ` → `can_read_all=false`. (Smoke: las escrituras Firestore se mockean / emulador — el smoke sqlite valida el outbox enqueue + dedup, no Firestore.)

### F3 — Handoff + outbound real + estados live (sin migración nueva)
- [ ] `services/conversation.py`: `take`/`release`/`close`/`reopen`/`mark_read` con los invariantes + `ConversationAssignmentLog` writes (`_close_current_log`/`_open_assignment_log`/`_reassign`) + **`enqueue_conversation_upsert`** (refleja assignee/allowed_reader_ids/unread en Firestore).
- [ ] **crm `lead_activity.log` extendido** (`related_conversation_id`) + emisión `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED`.
- [ ] `services/message.py`: `send_outbound` real (Meta Graph API via `get_credentials`; doc Firestore pending→sent/failed via Admin SDK; persiste fallido + 200).
- [ ] `routers/conversation.py`: take/release/close/reopen/mark-read + `POST /{id}/messages`.
- [ ] (Frontend F3) composer + controles de handoff + estados delivered/read en vivo (vía el listener) + `/conversaciones/mis-conversaciones` — ver [`ui.md`](ui.md).
- [ ] Test: `take` asigna actor + resetea unread + emite `CONVERSATION_TAKEN` (related_conversation_id) + cierra el log vigente y abre uno nuevo + encola `conversation_upsert` (allowed_reader_ids actualizado); `release` a unassigned emite `CONVERSATION_RELEASED`; `close` cierra log + `closed_at` + `status=closed` en Firestore; `reopen` con otra open → `409 CONVERSATION_ALREADY_OPEN`; `send_outbound` por no-assignee → `403 NOT_CONVERSATION_ASSIGNEE`; conversación cerrada → `400 CONVERSATION_NOT_OPEN`; envío fallido → 200 con doc Firestore `external_status=failed`; los eventos `CONVERSATION_*` NO son editables por el composer del asesor (404 vía `crm._get_editable_owned`).

### F4 — Adjuntos/media (DIFERIDA)
- [ ] Binarios → **GCS** (download del media de Meta, upload a un bucket, url firmada); el **doc Firestore del mensaje** lleva `attachments: [{type, url(GCS firmada), mime, ...}]` (NO hay tabla `message_attachment`). Cablear inbound/outbound media en `webhook_processor`/`send_outbound` + render UI. Texto-primero en F2/F3; fuera del MVP inicial.

> Flujo de cada fase = el de la metodología: leer fichas → backend e2e + smoke (sqlite create_all, RESULT=PASS+conteo a stdout) → frontend e2e (subagente contexto fresco) → tsc+build → review adversaria (Workflow 4 dims → verificación por hallazgo) → commit limpio (sin Co-Authored-By) → ff develop→qa → QA E2E con limpieza → **gate usuario (AskUserQuestion separado del merge)** → prod → PROD read-only → actualizar memoria. Backend venv: `backend/.venv/Scripts/{python,ruff,mypy}.exe`.

---

## 14. Notas operativas (gotchas)

- **revid Alembic ≤ 32 chars** (clinic F3 reventó con 34 → StringDataRightTruncation). `0015_conv_channel_account`=25, `0016_conv_threads`=17. ✔
- **Glob NO ve `app/modules/**`** (OneDrive dehydration) → Read con paths exactos.
- **`message_outbox.id` NO se autogenera**: lo setea el caller con el `mid` (wamid inbound / uuid outbound) → es la clave de idempotencia (`ON CONFLICT (id) DO NOTHING`). La columna es `varchar(255)` (el wamid de Meta es más largo que un uuid). Por eso `MessageOutbox` **NO hereda `PrimaryKeyMixin`** (que daría un `varchar(36)` autogen): declara su propio `id = mapped_column(String(255), primary_key=True)` en el modelo y la migración lo crea a 255 directo.
- **Firebase Admin import LAZY**: `import firebase_admin` SOLO dentro de las funciones de `app/core/firestore.py` (no al import del módulo) → el boot local / smoke sin GCP no rompe. El smoke (sqlite) NUNCA llama Firestore: mockear `app.core.firestore.*` o usar el emulador. Las escrituras del Admin SDK BYPASSAN las Security Rules (esas gobiernan solo al cliente Web).
- **Firestore Native mode obligatorio** (NO Datastore mode, NO Enterprise/MongoDB-compat) para listeners real-time + rules. Location `us-central1` es **permanente**. Una DB nombrada por entorno (`medisage-qa`/`medisage`), elegida por `ENV_NAME`.
- **ADC, no key file**: la SA de Cloud Run firma los custom tokens vía `signBlob` → necesita `roles/iam.serviceAccountTokenCreator` SOBRE SÍ MISMA + `roles/datastore.user`. NO meter un key file en Secret Manager.
- **`can_read_all` = (`CONVERSATIONS_READ` in permissions)**: es el claim que la Security Rule lee para dejar pasar al supervisor sin chequear `allowed_reader_ids`. El asesor común (solo `MY_CONVERSATIONS_READ`) → `can_read_all=false` → solo sus hilos (uid ∈ allowed_reader_ids). En logout / cambio de permisos: `firestore.revoke_tokens(uid)`.
- **El smoke (`create_all`, no alembic) NO ejercita la migración** (JSONB / ALTER ADD FK / partial index con `WHERE status='open'` son Postgres) → el `sqlite_where` en los modelos reproduce el índice parcial en el smoke; la FK aditiva, JSONB y el `ON CONFLICT` de Postgres se validan vía QA E2E sobre Postgres (en sqlite el `enqueue` usa el fallback get-then-insert). La review adversaria caza el drift Zod↔Pydantic y bugs de render que el smoke no ve (lección crm).
- **`raw_body` para la firma**: leer `await request.body()` ANTES de parsear JSON; re-serializar cambia los bytes y rompe el HMAC de Meta.
- **Relay SÍNCRONO antes del 200**: la TX Postgres (outbox) y el relay a Firestore corren ambos en el request, misma sesión, antes del 200 (`await relay_outbox(db)`). `BackgroundTasks` se descartó (no proyectaba en Cloud Run). El outbox es durable → si una fila queda `failed`/el proceso muere, un sweep/Cloud Task (`relay_outbox_in_new_session`, sesión propia) la recupera. Nunca se pierde un mensaje.
- **PowerShell 5.1**: no `&&`, `$pid` reservado (usar `$srvPid`), no `-SkipHttpErrorCheck`, IWR cuelga→curl.
- **`app/modules/__init__.py` hoy NO incluye `staff`** (tolerado por migraciones manuales) — incluir `conversations` igual (F1) para que Alembic/relationships lo registren.
- **`httpx`**: si no está en deps de runtime (solo test), agregarlo al `pyproject.toml` para `_meta_send_text` (cliente async outbound).
- **1 comando por call** en git/deploy; verificar que el verificador CORRIÓ (RESULT=PASS + conteo); gate de prod = AskUserQuestion separado del merge.
- **TZ**: `last_message_at`/`opened_at` se guardan tz-aware UTC (`utc_now()`); el render de "Hoy/Ayer" + day-groups del inbox va client-only (lección TZ recurrente — SSR en UTC desfasa el día en TZ negativas). Los timestamps de los docs Firestore también se guardan tz-aware UTC (el SDK los serializa como Firestore Timestamp).

---

## 15. Decisiones para ADRs / consolidación

- **ADR-011 (NUEVO, Accepted, 2026-06-03)**: "Stream de mensajes en Firestore (CQRS read-model) — control plane Postgres + data plane Firestore + Transactional Outbox + Custom-Token auth". **Context**: por qué Firestore para el real-time del inbox (real-time client sync nativo) y por qué CQRS y no dual-store ingenuo (industria: wide-column a escala; Firestore por su sync real-time del cliente). **Decision**: el split de §1 del brief (Postgres = `channel_account`/`conversation`/`conversation_assignment_log`/`message_outbox`; Firestore = `conversations/{cid}` + `conversations/{cid}/messages/{mid}`), el outbox §2 (idempotencia outbox-id + doc-id), la auth §3 (Custom Tokens + Security Rules con `allowed_reader_ids`/`can_read_all`). **Alternatives**: todo Postgres + polling (RECHAZADA: sin real-time nativo); todo Postgres + SSE (viable, descartada a favor de Firestore por el usuario); todo a Firestore incl. Conversation (RECHAZADA: rompe FK crm + queries relacionales del inbox); dual-write sin outbox (RECHAZADA: inconsistencia). **Consequences**: real-time + sin pérdida de mensajes; complejidad (Firestore + Firebase Admin + outbox + relay + rules + 2º SDK + costo de reads), mitigada por el aislamiento CQRS (Postgres sigue siendo la fuente de verdad; Firestore es proyección desechable/reconstruible). Referencia a ADR-004 (revisado) y ADR-010 (secretos).
- **ADR-004 (REVISAR, mantener Accepted, "act. 2026-06-03")**: **Message YA NO es entidad Postgres relacional** — pasa a Firestore como read-model (ver ADR-011); `Conversation`/`ChannelAccount`/`conversation_assignment_log`/`message_outbox` quedan en Postgres (control plane); la **idempotencia ahora es outbox-unique (`message_outbox.id`=mid) + doc-id Firestore**, NO el UNIQUE parcial `(conversation_id, external_id)` de `message`. Además (ya estaba): corregir la afirmación errónea sobre Secret Manager (inyección por env vía `--set-secrets`; SDK runtime → ADR-010); PATCH→PUT; auto-asignación al dueño del lead (con fallback unassigned), texto-primero en adjuntos (binarios a GCS, doc lleva `attachments[]`), webhook síncrono + relay del outbox SÍNCRONO en el request (BackgroundTasks descartado; cola/Cloud Tasks para auto-reply lento de bots), emisión solo `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED` (no `MESSAGE_SENT` por-mensaje), hardening de `find_by_identifier_or_create` con advisory lock, FK aditiva `related_conversation_id`.
- **ADR-010 (nuevo, Accepted)**: "Resolución de secretos por-cuenta vía Secret Manager SDK en runtime (cacheado)". Contexto: el template inyecta secretos fijos por env (deploy-time); las credenciales por-ChannelAccount necesitan resolución dinámica para multi-cuenta sin redeploy. Decisión: SDK `google-cloud-secret-manager` + `app/core/secrets.py` con cache TTL + fallback env (local/test). Alternativas: inyección por env (descartada: 1 número por deploy), columna cifrada en BD (descartada: secreto en backups). Reusable por futuros módulos con secretos por-tenant/cuenta. (El Firebase Admin NO usa Secret Manager → usa ADC, ADR-011.)
- **Diagramas**: regenerar `er-conversations.puml` (quitar tablas `message`/`message_attachment`; agregar `message_outbox` Postgres; mostrar Firestore como store externo `<<external, Firestore>>` con `conversations/{cid}` + `.../messages/{mid}` y la relación `conversation 1—projection→ firestore doc`; mantener `channel_account`/`conversation`/`conversation_assignment_log`/`lead_activity` con la FK aditiva; anotar `channel_type` = reuse `crm.ChannelType`; `bot_configuration_id`/`default_campaign_id` = forward sin constraint ADR-009) y `class-backend-conversations.puml` (agregar `app/core/firestore.py` Admin SDK, `message_outbox` model+repo, el relay, el `realtime` router; `message.py` service ahora habla con Firestore (Admin SDK) + outbox; quitar los modelos `Message`/`MessageAttachment` Postgres → "Firestore docs" anotados; secret_resolver en `app.core`; webhook_processor; auto-asignación; helpers crm consumidos). PATCH→PUT en cualquier referencia.
- **Overview viejo**: borrar `docs/modules/conversations.md` (consolidado en el README) y repuntar TODOS sus links (`grep "modules/conversations.md"`) al `conversations/README.md`.
- **Memoria**: crear `project_medisage_conversations_plan.md` + puntero en MEMORY.md.
