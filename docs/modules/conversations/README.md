# Módulo `conversations`

> **Última actualización**: 2026-06-03 (rediseño CQRS — stream de mensajes en Firestore; ver [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md))
> **Propósito**: el **dueño del pipe de mensajería multicanal**. Recibe mensajes **inbound** desde los webhooks de los proveedores (WhatsApp Cloud API en el MVP), los persiste, identifica al `Person` que escribe vía `crm.find_by_identifier_or_create`, deja la conversación en la **bandeja del asesor** (auto-asignada al dueño del lead, con fallback a bandeja compartida) y permite responder **outbound real** contra la Graph API de Meta. Es el **módulo #5** del proyecto — se construye sobre `crm` y deja columnas forward listas para `bots` (#6) y `marketing` (#8).
> **Path del código**: `backend/app/modules/conversations/` (backend) · `frontend/src/app/(main)/conversaciones/` (frontend). Webhooks **top-level** (sin JWT) en `backend/app/routers/webhooks.py`.

> **Este documento es el overview** (fuente de verdad consolidada del módulo; el overview viejo `docs/modules/conversations.md` queda borrado y sus links repuntan aquí). Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts (request/response/errores), lógica de service, webhook processor, secret resolver, draft SQL de las migraciones.
> - 🎨 [`ui.md`](ui.md) — mockups por pantalla con estados (empty/loading/no-results/error), el **inbox 2-paneles** (la UI más pesada del módulo), componentes Fluent UI, UX writing en español.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación, types espejo, polling.

## Resumen

`conversations` es donde la clínica **conversa** con sus contactos. Un mensaje de WhatsApp entra por un webhook, el sistema lo deduplica y lo persiste, resuelve **quién** lo manda contra `crm` (creando la `Person` + lead si es la primera vez), y la conversación aparece en la bandeja del asesor responsable de ese lead. El asesor **toma** la conversación, responde (envío real a Meta), y al **liberar** o **cerrar** deja la traza en el timeline del lead. Es un módulo de **infraestructura de mensajería + bandeja humana** — no contiene inteligencia de bot (eso llega en `bots` #6); en el MVP cada mensaje saliente lo escribe una persona.

```
  Proveedor (Meta WhatsApp Cloud API)
        │  POST /api/v1/webhooks/whatsapp/{channel_account_id}   (sin JWT)
        ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ app/routers/webhooks.py  (router top-level)                        │
  │   1. carga ChannelAccount(id)            → 404 si no existe/inactivo│
  │   2. secret_resolver.get_credentials(ca) → app_secret              │
  │   3. valida X-Hub-Signature-256 (HMAC SHA256 del body RAW)         │
  │        mismatch → 403 WEBHOOK_SIGNATURE_INVALID (sin tocar BD)     │
  └───────────────────────────────┬──────────────────────────────────┘
                                   │ delega (síncrono, antes del 200)
                                   ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ services/webhook_processor/whatsapp.py : process_inbound(...)      │
  │   TX Postgres ATÓMICA (control plane = fuente de verdad):          │
  │     crm.find_by_identifier_or_create(whatsapp, phone, profile)     │ ──▶ crm
  │       (Person + identifier + lead inicial + round-robin)           │
  │     conversation.find_or_create_open(person, channel_account)      │
  │       auto-asigna al dueño del lead (advisor_map) / unassigned     │
  │     INSERT message_outbox(id=mid, op=message_create) ON CONFLICT   │
  │       DO NOTHING  → dedup real; si nuevo: unread++,                │
  │       last_message_at/preview + outbox(op=conversation_upsert)     │
  │   COMMIT  (si algo falla, NADA se aplica)                          │
  └───────────────────────────────┬──────────────────────────────────┘
                  │ relay (BackgroundTasks MVP / Cloud Tasks prod)
                  ▼ Firebase Admin SDK: set(doc_id=mid)
  ┌──────────────────────────────────────────────────────────────────┐
  │ Firestore (data plane / read-model real-time)                     │
  │   conversations/{cid}            (doc espejo)                      │
  │   conversations/{cid}/messages/{mid}  (el mensaje)                │
  └───────────────────────────────┬──────────────────────────────────┘
                                   ▼ onSnapshot (listener read-only)
  ┌──────────────────────────────────────────────────────────────────┐
  │ Inbox del asesor (Next.js): thread real-time vía Firestore;       │
  │   listado por polling Postgres ~10s                               │
  │   Tomar → responder (outbound real a Meta) → Liberar / Cerrar      │
  │   take/release emiten CONVERSATION_TAKEN/RELEASED a crm.LeadActivity│ ──▶ crm
  └──────────────────────────────────────────────────────────────────┘
```

El modelo nace **multicanal** aunque el MVP solo cablee WhatsApp: `channel_type` reusa el enum `crm.ChannelType`, y agregar Telegram/web/Instagram es un `processor` nuevo por canal + una URL de webhook nueva — **sin migración** (el enum y las tablas ya lo soportan). Las credenciales por número viven en **GCP Secret Manager** resueltas en runtime ([ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md)), así que la clínica puede operar **N números sin redeploy**.

## Posición y dependencias

`conversations` es el **#5** del orden de medisage (catalog → clinic → staff → **crm** COMPLETOS en prod → conversations → bots #6 → scheduling #7 → marketing #8). Depende de:

| Módulo | Relación | FK |
|---|---|---|
| `admin` | `Conversation.assignee_user_id`, `ConversationAssignmentLog.{from,to}_assignee_user_id`/`by_actor_user_id` → `user.id` (FK real Postgres). El `sender_user_id` del mensaje vive en el doc Firestore (varchar, sin constraint — Firestore no tiene FKs). Audit users (`created_by`/`updated_by`). El user `SYSTEM` (seed de crm F0) es el `created_by` de los inbound automáticos. | **FK real** (ya existe `user`). |
| `crm` | Resuelve `Person` vía `find_by_identifier_or_create`; lee el dueño del lead (`lead_assignment_repository.advisor_map`) para auto-asignar; emite `LeadActivity(CONVERSATION_TAKEN/RELEASED)`; `Conversation.person_id` → `person.id`. Agrega la **FK constraint aditiva** a `lead_activity.related_conversation_id`. | **FK real** a `person`; **FK aditiva** a `lead_activity`. |
| `bots` (#6, NO existe) | `ChannelAccount.bot_configuration_id`, `Conversation.bot_configuration_id` (Postgres) y `bot_configuration_id` en el doc del mensaje (Firestore) apuntan al bot efectivo. | **FK forward** ([ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md)): `varchar(36)` sin constraint/relationship en Postgres; campo libre en el doc Firestore. Hoy SIEMPRE NULL. |
| `marketing` (#8, NO existe) | `ChannelAccount.default_campaign_id` → se pasa a `find_by_identifier_or_create(campaign_id=...)` para atribución. | **FK forward** (ADR-009). Hoy NULL. |

Migración cabeza actual = `0014_crm_customer_lifecycle`. Las de conversations: **`0015_conv_channel_account`** y **`0016_conv_threads`**.

## Entidades

**Arquitectura CQRS** (ver [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md)): el **stream de mensajes vive en Firestore** (data plane / read-model real-time), no en Postgres. Postgres es el **control plane** (fuente de verdad relacional/operativa): **4 tablas** (`channel_account`, `conversation`, `conversation_assignment_log`, **`message_outbox` NUEVO**). Firestore (Native mode) aloja **2 colecciones** (`conversations/{cid}` doc espejo + `conversations/{cid}/messages/{mid}` el mensaje). Las tablas Postgres `message`/`message_attachment` **ya no existen** — su contenido pasó a docs Firestore (los enums/Pydantic schemas del mensaje SE MANTIENEN como contrato de API + shape del doc).

### Tablas Postgres (control plane)

Mixins: `PK`=`PrimaryKeyMixin` (id varchar(36)), `A`=`ActiveMixin` (active bool), `SD`=`SoftDeleteMixin` (deleted_at), `T`=`TimestampMixin` (created_on/by, updated_on/by). **Los logs NO llevan `SD`** (audit trail inmutable — ver [Decisiones](#mensajes-y-logs-sin-softdelete-audit-inmutable)).

| Entidad | Tabla | Mixins | Propósito |
|---|---|---|---|
| `ChannelAccount` | `channel_account` | PK·A·SD·T | Cuenta de canal de la clínica (config + ref al secreto). Un número de WhatsApp Business = una fila. |
| `Conversation` | `conversation` | PK·A·SD·T | Hilo `Person ↔ ChannelAccount`. `UNIQUE` parcial → **una sola open** por par. Control plane: **NO se va a Firestore** (preserva la FK `lead_activity.related_conversation_id`, el UNIQUE 1-open y los filtros SQL del inbox). |
| `ConversationAssignmentLog` | `conversation_assignment_log` | PK·A·T (SIN SD) | Historial inmutable de handoff (tomar/liberar/reasignar). |
| `MessageOutbox` | `message_outbox` | PK·A·T (SIN SD) | **NUEVO** — cola transaccional durable Postgres→Firestore (Transactional Outbox). Garantiza el sync sin transacción distribuida ni pérdida. |

### Colecciones Firestore (data plane — read-model real-time)

Native mode (Standard edition, requerido para listeners real-time del Web SDK + Security Rules). **Una database por entorno** (named DBs `medisage-qa` / `medisage`, espejando Cloud SQL; el backend elige por `ENV_NAME`), location `us-central1`. Escritas **solo por el backend** (Firebase Admin SDK, que bypassa las rules); el browser solo **lee** (listeners read-only, ver [Persistencia de mensajes](#persistencia-de-mensajes-firestore-cqrs--control-plane-postgres--data-plane-firestore)).

| Colección | Doc id | Propósito |
|---|---|---|
| `conversations/{cid}` | `cid` = UUID del `Conversation` de Postgres (clave de join) | Espejo liviano del Conversation para las Security Rules + el inbox live. Shape: `{ status, assignee_user_id, allowed_reader_ids: [uid...], channel_account_id, person_name, person_id, last_message_at, last_message_preview, unread_count, updated_at }`. |
| `conversations/{cid}/messages/{mid}` | `mid` = `wamid` (inbound) / uuid (outbound) → **idempotencia natural** | El mensaje. Shape: `{ direction, sender_type, sender_user_id, bot_configuration_id, content_type, content, external_id, external_status, sent_at, delivered_at, read_at, failed_at, failure_reason, attachments: [...], provider_payload, created_at }` (snake_case, alineado con el contrato Pydantic). |

### `ChannelAccount`

Cuenta de canal (un número WhatsApp Business) con su configuración y la **referencia** (no el valor) de su secreto.

- `channel_type: varchar(40)` NOT NULL — **slug de `crm.enums.ChannelType`** (reuse, no se duplica el enum). Valor MVP: `whatsapp`.
- `name: varchar(120)` NOT NULL — nombre humano ("WhatsApp Estética").
- `external_identifier: varchar(255)` NOT NULL — id del proveedor (número WA Business, ej. `51999111222`).
- `secret_name: varchar(255)` nullable — **nombre del secreto en GCP Secret Manager** (ej. `medisage-whatsapp-estetica-qa`). El `secret_resolver` lo resuelve en runtime → `{access_token, app_secret, phone_number_id?}`. NULL = fallback a env (local/dev). **El valor del secreto nunca se expone en ningún schema.**
- `webhook_verify_token: varchar(255)` nullable — challenge de verificación de Meta (GET). No es secreto duro (lo envía Meta y se compara) → columna directa, editable en la UI.
- `phone_number_id: varchar(64)` nullable — id del número en WhatsApp Cloud API, para construir la URL de envío `/{phone_number_id}/messages`. (Vive en columna por practicidad de la URL; puede venir también del secreto.)
- `bot_configuration_id: varchar(36)` nullable — **FK forward** (bots, ADR-009). Bot por defecto del canal. Hoy NULL.
- `default_campaign_id: varchar(36)` nullable — **FK forward** (marketing, ADR-009). Campaña de atribución → se pasa a `find_by_identifier_or_create(campaign_id=...)`. Hoy NULL.
- **UNIQUE parcial** `(channel_type, external_identifier) WHERE deleted_at IS NULL` (dialect-agnóstico: `postgresql_where` + `sqlite_where`). Violación → `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` (409).

### `Conversation`

Hilo entre una `Person` y una `ChannelAccount`. `UNIQUE` parcial garantiza **una sola conversación open** por par.

- `channel_account_id: varchar(36)` NOT NULL — **FK real** → `channel_account.id`.
- `person_id: varchar(36)` nullable — **FK real** → `person.id`. NULL solo en la ventana corta antes de resolver; en práctica siempre poblado tras `find_by_identifier_or_create`.
- `status: varchar(20)` NOT NULL — `ConversationStatus`: `open` / `closed`.
- `assignee_type: varchar(20)` NOT NULL — `AssigneeType`: `bot` / `advisor` / `unassigned`.
- `assignee_user_id: varchar(36)` nullable — **FK real** → `user.id`. NOT NULL ⟺ `assignee_type='advisor'`.
- `bot_configuration_id: varchar(36)` nullable — **FK forward** (bots). Bot efectivo (puede diferir del default del canal). Hoy NULL.
- `opened_at: timestamptz` NOT NULL · `closed_at: timestamptz` nullable.
- `last_message_at: timestamptz` nullable — denormalizado (sort/inbox; `defaultSort`).
- `last_message_preview: varchar(255)` nullable — primeros 255 chars del último mensaje (inbox).
- `unread_count: int` NOT NULL default 0 — incrementa por inbound; resetea en `mark-read`/`take`.
- **UNIQUE parcial** `(person_id, channel_account_id) WHERE status='open' AND deleted_at IS NULL` (dialect-agnóstico → "una sola open" + reabrir tras cerrar).
- **Invariantes** (validados en service, code propio):
  - `assignee_type='advisor'` ⇒ `assignee_user_id NOT NULL` (sino `INVALID_ASSIGNEE` 400).
  - `assignee_type ∈ {bot, unassigned}` ⇒ `assignee_user_id IS NULL`.
  - `assignee_type='bot'` ⇒ `bot_configuration_id NOT NULL` (no aplica en MVP — bots no existe).
  - Cerrar (status=closed) ⇒ cierra el `ConversationAssignmentLog` vigente (`ended_at=now`).
  - Cambio de assignee ⇒ cierra el log vigente + abre uno nuevo, en la misma tx.

### `MessageOutbox` (NUEVO — Transactional Outbox, SIN SoftDelete)

Cola transaccional durable Postgres→Firestore. Se escribe **dentro de la misma TX** que muta el control plane (consistencia sin transacción distribuida); un **relay** lee los pendientes y los escribe a Firestore con el Admin SDK (`set(doc_id=mid)` → create-if-absent idempotente). **Nunca pierde un mensaje** (vive en el outbox tras el commit aunque el relay falle; reintenta con backoff).

- `id: varchar(36)` PK — **= el `mid` del mensaje** (`wamid` inbound / uuid outbound). **UNIQUE** → da la idempotencia (`INSERT ... ON CONFLICT (id) DO NOTHING` = dedup real; el `unread_count++` solo corre si el insert fue nuevo).
- `conversation_id: varchar(36)` NOT NULL — **FK real** → `conversation.id`.
- `op: varchar(40)` NOT NULL — `message_create` / `message_status` / `conversation_upsert` (qué doc reflejar en Firestore).
- `payload: JSON().with_variant(JSONB, "postgresql")` NOT NULL — el doc a escribir en Firestore. Misma técnica que `crm.lead_activity.payload`: JSON en sqlite/create_all, JSONB en la migración Postgres.
- `status: varchar(20)` NOT NULL default `pending` — `pending` / `done` / `failed`.
- `attempts: int` NOT NULL default 0 · `last_error: varchar(1000)` nullable.
- `created_on: timestamptz` (mixin `T`) · `processed_on: timestamptz` nullable.
- **Índice** `(status, created_on)` para que el relay barra los pendientes en orden.

> Los **mensajes** ya **no son una tabla Postgres** — viven en Firestore (`conversations/{cid}/messages/{mid}`, shape arriba), inmutables y sin SoftDelete por la misma razón de auditoría honesta. El `mid` (= `wamid` inbound / uuid outbound) es el doc id → la idempotencia es **outbox-unique + doc-id**, reemplaza el UNIQUE parcial `(conversation_id, external_id)` que tenía la tabla `message` (ver [Idempotencia](#idempotencia-outbox-unique--doc-id)). Los **adjuntos** (`MessageAttachment`) también dejan de ser tabla: el doc del mensaje lleva `attachments: [...]` inline (binarios → GCS en F4, igual que antes; texto-primero en F2/F3).

### `ConversationAssignmentLog` (SIN SoftDelete — audit inmutable)

Historial de handoff (paralelo al `LeadStatusHistory`/`LeadAssignment` de crm). Cada cambio de assignee abre una fila y cierra la anterior.

- `conversation_id: varchar(36)` NOT NULL — **FK real** → `conversation.id`.
- `from_assignee_type: varchar(20)` nullable (NULL en el primer log) · `from_assignee_user_id: varchar(36)` nullable — **FK real** → `user.id`.
- `to_assignee_type: varchar(20)` NOT NULL · `to_assignee_user_id: varchar(36)` nullable — **FK real** → `user.id`.
- `started_at: timestamptz` NOT NULL · `ended_at: timestamptz` nullable (NULL = vigente).
- `by_actor_user_id: varchar(36)` nullable — **FK real** → `user.id`. NULL = automático (sistema/auto-asignación).
- `reason: varchar(255)` nullable.

## Enums (en código)

`ChannelType` se **REUSA de `crm.enums`** — single source of truth (el docstring de crm ya dice "the slug crosses with conversations.ChannelAccount.channel_type"). conversations hace `from app.modules.crm.enums import ChannelType`; **NO duplica** el enum. Valores: `whatsapp/telegram/web/phone/email/instagram/facebook/other`.

Enums conversations-owned (`app/modules/conversations/enums.py`, `StrEnum` por ruff `UP042`):

| Enum | Valores |
|---|---|
| `ConversationStatus` | `open`, `closed` |
| `AssigneeType` | `bot`, `advisor`, `unassigned` |
| `MessageDirection` | `inbound`, `outbound` |
| `SenderType` | `contact`, `bot`, `advisor`, `system` |
| `ContentType` | `text`, `image`, `audio`, `video`, `document`, `location`, `sticker`, `contact_card`, `system_notification` |
| `AttachmentType` | `image`, `audio`, `video`, `document`, `location`, `sticker`, `contact_card` |
| `MessageExternalStatus` | `sent`, `delivered`, `read`, `failed` (valores conocidos; la columna es varchar libre) |

## Enganche con `crm` (verificado en código) + cambios aditivos

`conversations` consume tres puntos de `crm` y agrega **dos cambios aditivos backward-compatible** + **una FK aditiva**. Todo verificado contra el código real (`crm/services/person.py`, `lead_activity.py`, `enums.py`, `models/lead_activity.py`).

### 1. `find_by_identifier_or_create` (lo invoca el webhook processor)

Firma real (`crm/services/person.py:411`):

```python
async def find_by_identifier_or_create(
    db, channel_type: ChannelType, identifier: str, profile: PersonCreate, *, campaign_id: str | None = None
) -> Person
```

conversations la llama con: `channel_type=ChannelType.whatsapp`, `identifier=<phone>`, `profile=PersonCreate(first_name=pushname.trim()[:80] o "Contacto", last_name="(WhatsApp)", identifiers=[])`, `campaign_id=channel_account.default_campaign_id`. La función crea (si no existe) Person + identifier (`is_primary`, NO verificado) + `PersonLeadStatus(is_initial)` + `LeadStatusHistory(NULL→initial)` + `LeadAssignment(round-robin)` + `LeadActivity(CAMPAIGN_ATTRIBUTION)` si hay `campaign_id`; `created_by = SYSTEM_USER_ID`; idempotente por identifier. **`profile.identifiers` se ignora** (la función construye el identifier ella misma del par `(channel_type, identifier)`) → se pasa lista vacía. **Contacto desconocido** → `first_name = pushname.trim()[:80]` o `"Contacto"`, `last_name = "(WhatsApp)"` (el `min_length=1` de `last_name` lo exige; placeholder editable por el asesor).

**CAMBIO ADITIVO #1 a crm (hardening de concurrencia)** — hoy `find_by_identifier_or_create` hace get-then-insert **sin lock** (no tenía callers). Bajo webhooks concurrentes para el MISMO número nuevo, dos requests pasan el `get_by_identifier` (ambos NULL) e insertan → `IntegrityError`. Fix: **advisory lock transaccional Postgres** al inicio de la función, keyed por `(channel_type, identifier)`:

```python
if db.bind.dialect.name == "postgresql":
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"{channel_type.value}:{identifier}", 0))))
```

(sqlite: no-op; el smoke es single-thread.) Serializa el get-then-insert por identifier; el lock se libera al fin de la tx. La hardening vive **DENTRO de crm** (la función dueña del dedup) y beneficia a cualquier caller. Alternativa documentada (no elegida): try/except `IntegrityError` → rollback parcial → re-get; descartada por la fricción con la sesión-por-request (un rollback aborta toda la tx del webhook).

### 2. `lead_activity.log` (lo invoca conversations para emitir eventos de sistema)

Firma real (`crm/services/lead_activity.py:85`): `log(db, person_id, activity_type, *, advisor_user_id, actor_id, content?, scheduled_for?, completed_at?, outcome?, payload?) -> LeadActivity`. **NO** hace flush/commit; toca `last_activity_at` del lead activo si existe.

**CAMBIO ADITIVO #2 a crm**: agregar parámetro opcional `related_conversation_id: str | None = None` a `log`, y `activity.related_conversation_id = related_conversation_id` en el constructor de `LeadActivity` (la columna ya existe — `models/lead_activity.py:51`). Backward-compatible (los callers existentes —`person.find_by_identifier_or_create`, `person_lead_status.transition`, `lead_assignment.reassign`— no lo pasan). conversations emite **solo dos** tipos:

- `CONVERSATION_TAKEN` al tomar: `log(db, person_id, ActivityType.CONVERSATION_TAKEN, advisor_user_id=actor, actor_id=actor, related_conversation_id=conv.id, payload={"channel_account_id": ...})`.
- `CONVERSATION_RELEASED` al liberar: análogo (`advisor_user_id` = el asesor que libera).
- **NO** `MESSAGE_SENT` por-mensaje (decisión §1 de la spec — evita inundar el timeline lead-céntrico y la escritura cross-módulo en el hot path del envío). `MESSAGE_SENT` queda en el enum para un uso futuro (ej. "primer contacto").

Estos eventos NO están en `ADVISOR_ACTIVITY_TYPES` → el composer del asesor de crm **NO puede editarlos/borrarlos** (`_get_editable_owned` ya lo impone → 404 `ACTIVITY_NOT_FOUND`). Audit trail inmutable. ✔ (verificado en `lead_activity.py:172`).

### 3. Leer el dueño del lead (auto-asignación) — sin cambio a crm

Al crear una conversación nueva, conversations usa el repo existente `lead_assignment_repository.advisor_map(db, [person_id])` (devuelve `{person_id: advisor_user_id}` del lead activo) para resolver el asesor de la Person: si hay → `assignee_type='advisor'`, `assignee_user_id=advisor`; si no → `unassigned` (bandeja compartida). Lectura aditiva, sin cambio a crm. El asesor puede tomar/reasignar igual ("mis leads = mis chats").

### 4. FK forward `lead_activity.related_conversation_id` (conversations es el dueño)

La columna existe en crm (`varchar(36)` + index, **sin** constraint, ADR-009). conversations agrega la **constraint aditiva** en su migración de threads (F2), Postgres-only:

```python
op.create_foreign_key("fk_lead_activity_conversation", "lead_activity", "conversation", ["related_conversation_id"], ["id"])
```

Seguro (todos los valores actuales son NULL). **NO** se agrega `relationship` ORM (mantiene el modelo crm intacto, consistente con el patrón "sin relationship cross-módulo"). Caveat sqlite: el `ALTER ADD FK` no corre en sqlite/create_all (la migración solo corre en Postgres; el smoke usa create_all → no ejercita la FK aditiva).

## Webhooks (top-level, `app/routers/webhooks.py`, sin JWT)

**Estructura nueva**: hoy NO existe `app/routers/`. Se crea `backend/app/routers/__init__.py` + `webhooks.py` (router top-level), registrado en `app/main.py` con prefix `settings.API_V1_PREFIX` (`/api/v1`). La lógica vive en `app/modules/conversations/services/webhook_processor/<canal>.py` (cohesión por dominio); el router solo valida firma y delega.

| Método | Ruta | Auth | Propósito |
|---|---|---|---|
| GET | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT; compara `hub.verify_token` con `ChannelAccount.webhook_verify_token` | Meta verification challenge → devuelve `hub.challenge` (200) o 403 |
| POST | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT; valida `X-Hub-Signature-256` (HMAC SHA256 del body **raw** con `app_secret`) | inbound messages + status callbacks |

`telegram` queda **diferido** (URL futura `/api/v1/webhooks/telegram/{channel_account_id}` con `X-Telegram-Bot-Api-Secret-Token`); el modelo/enum ya lo soportan, solo falta el `processor`.

### Flujo inbound (síncrono, MVP sin bot) — TX Postgres + outbox + relay a Firestore

1. Router carga `ChannelAccount` por id (404/inactivo → 404, sin procesar).
2. `secret_resolver.get_credentials(ca)` → `app_secret`. Valida `X-Hub-Signature-256` sobre el body raw. Mismatch → **403** `WEBHOOK_SIGNATURE_INVALID` (rápido, sin tocar BD).
3. Delega a `webhook_processor/whatsapp.py:process_inbound(payload, channel_account, db)`.
4. **TX Postgres ATÓMICA** (control plane = fuente de verdad), por cada `messages[]`:
   a. `crm.find_by_identifier_or_create(...)` (hardened, advisory lock) → Person + lead inicial + round-robin.
   b. `conversation.find_or_create_open(person, channel_account)` → auto-asigna al dueño del lead (advisor_map) / unassigned.
   c. `INSERT message_outbox(id=mid, op=message_create, payload=...) ON CONFLICT (id) DO NOTHING` → **dedup real** (idempotencia).
   d. **Solo si (c) insertó algo nuevo**: `unread_count++`, `last_message_at`/`preview` en `conversation` + `INSERT message_outbox(op=conversation_upsert, ...)` para reflejar el doc espejo.
   e. `lead_activity.log(...)` si corresponde. **SIN dispatch a bot** (no existe).
   **COMMIT** (si algo falla, NADA se aplica; el mensaje no se pierde — vive en el outbox tras el commit).
5. **Relay** (MVP `BackgroundTasks` tras el 200; producción/durable Cloud Tasks): lee `message_outbox` pendientes y los escribe a Firestore con el Admin SDK (`set(doc_id=mid)` → create-if-absent idempotente); marca `done`, reintenta con backoff (`attempts`/`last_error`).
6. **Status callbacks** (`statuses[]` delivered/read/failed): el backend actualiza **directo el doc Firestore** `conversations/{cid}/messages/{mid}` vía Admin SDK (real-time; NO toca Postgres — el status es best-effort; puede ir por outbox `op=message_status` para durabilidad).
7. Return **200** (tras la TX; el relay corre aparte). Error inesperado → 500 (Meta reintenta; la idempotencia outbox-unique + doc-id evita duplicados).

> **Webhook síncrono en el MVP** (decisión §1): el procesamiento es rápido (verify firma + dedup + resolver Person + escribir outbox) y no hay bot que genere auto-reply lento, así que la **TX Postgres** se procesa **antes** del 200; el relay a Firestore corre aparte (`BackgroundTasks`). Cuando `bots` agregue auto-reply lento → mover a cola / `--no-cpu-throttling --min-instances 1`.

### Flujo outbound (autenticado, `POST /conversations/{id}/messages`)

1. Carga conversation (404). `status=open` (sino `CONVERSATION_NOT_OPEN` 400).
2. Autorización: `actor == conversation.assignee_user_id` y `assignee_type='advisor'` (sino `NOT_CONVERSATION_ASSIGNEE` 403). (Admin con permiso aparte = futuro.)
3. **TX Postgres**: `INSERT message_outbox(id=uuid, op=message_create, payload status=pending)` + `unread`/`last_message` denorm + `conversation_upsert`. **COMMIT**.
4. Relay/inline escribe el doc Firestore (status=pending) → el asesor lo ve **instantáneo** vía su listener.
5. `secret_resolver.get_credentials(ca)` → `access_token` + `phone_number_id`. Llama Meta Graph API (`POST https://graph.facebook.com/v<ver>/{phone_number_id}/messages`). Éxito → **update doc Firestore** `{external_id, external_status: sent, sent_at}`. Falla → `{failed_at, failure_reason, external_status: failed}` en el doc; **return 200** con el message fallido (UI muestra reintento), **NO 502** (decisión §1).
6. **NO** emite `MESSAGE_SENT` a crm (§1). Reintento = mensaje nuevo (mid uuid nuevo).

## Secret resolver (Secret Manager SDK, runtime, cache) — ADR-010

- Dependencia nueva: `google-cloud-secret-manager` (pin en `pyproject.toml`).
- Módulo `app/core/secrets.py` (cross-cutting, **reusable** — lo consumirá también bots si necesita secretos por-cuenta).
- API: `async def resolve(secret_name: str) -> dict` (parsea el secreto como JSON `{access_token, app_secret, phone_number_id?}`) con **cache TTL (≈10 min)** en memoria (dict + monotonic clock) para no golpear Secret Manager por webhook.
- `conversations.services.channel_account.get_credentials(ca) -> dict`: si `ca.secret_name` set → `secrets.resolve(ca.secret_name)`; si NULL o `ENV_NAME=dev`/`USE_LOCAL_SECRETS` → fallback a env (`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, etc. en `Settings`). Vacío/404 → `CHANNEL_CREDENTIALS_MISSING`.
- Local/test: el smoke (sqlite) **NUNCA** llama Secret Manager (usa fallback env / mock). El cliente SDK se inicializa **lazy** (no al import) para no romper el boot sin GCP.
- Cloud Run: la SA ya tiene `roles/secretmanager.secretAccessor`. Crear los secretos por env (`medisage-whatsapp-*-{qa,prod}`) al desplegar F1/F2 (ver checklist de deploy).

> **Dos resolvers distintos.** Además del `secret_resolver` de WhatsApp (ADR-010, vía Secret Manager SDK), el módulo usa un **Firebase Admin SDK** (`app/core/firestore.py`, Python `firebase-admin`) para mintear los custom tokens del browser + escribir Firestore. El Admin SDK se inicializa vía **ADC** (la SA de Cloud Run `medisage-sa[-qa]`, sin key file en prod), con roles `roles/datastore.user` (Firestore RW) + `roles/iam.serviceAccountTokenCreator` sobre sí misma (para firmar custom tokens vía signBlob). Local/dev: ADC de gcloud o key file. **NO** se mete un key file en Secret Manager (ADC es más robusto). Ver [Persistencia de mensajes](#persistencia-de-mensajes-firestore-cqrs--control-plane-postgres--data-plane-firestore) y [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md).

## Endpoints (resumen)

Todos bajo `/api/v1/conversations/` (aggregator `app/modules/conversations/routers/__init__.py` con `APIRouter(prefix="/conversations")`, incluido en `main.py`, molde crm). Convención del codebase: **`PUT` (no `PATCH`)**; **`POST /<recurso>/list`** para listados paginados; **`/active`** para dropdowns (lista cruda). El detalle de request/response/errores está en [`backend.md`](backend.md#api-contracts).

| Método | Ruta | Permiso | Notas |
|---|---|---|---|
| POST | `/channel-accounts/list` | `CHANNEL_ACCOUNTS_READ` | `PaginatedResponse[ChannelAccountItem]` |
| POST | `/channel-accounts` | `CHANNEL_ACCOUNTS_CREATE` | `SingleResponse[ChannelAccountDetail]` |
| GET | `/channel-accounts/active` | `CHANNEL_ACCOUNTS_READ` | lista cruda `ChannelAccountOption` (selects/filtros) |
| GET | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_READ` | `SingleResponse[ChannelAccountDetail]` |
| PUT | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_UPDATE` | |
| DELETE | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_DELETE` | soft-delete |
| POST | `/list` | `CONVERSATIONS_READ` | inbox global. `PaginatedResponse[ConversationListItem]`. Deep-links: `?channel_account_id`/`?status`/`?assignee_user_id`/`?unassigned` |
| GET | `/{id}` | `CONVERSATIONS_READ` | `SingleResponse[ConversationDetail]` (+ `assignment_history`) |
| POST | `/realtime/token` | `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` | **NUEVO** — mintea el custom token de Firebase (`{ token, firebase_config? }`) para que el browser abra listeners read-only. El JWT/RBAC gatea quién recibe token y con qué claims (`can_read_all` para `CONVERSATIONS_READ`). Ver [Persistencia de mensajes](#persistencia-de-mensajes-firestore-cqrs--control-plane-postgres--data-plane-firestore) |
| POST | `/{id}/messages/list` | `MESSAGES_READ` | **FALLBACK** — `PaginatedResponse[MessageItem]` (lee Firestore vía Admin SDK server-side, para SSR/fallback). El path **primario** de lectura del hilo es el cliente Firestore real-time (`onSnapshot`) |
| POST | `/{id}/messages` | `MESSAGES_SEND` | enviar outbound (escribe outbox + Firestore + Meta server-side). `SingleResponse[MessageItem]` |
| POST | `/{id}/take` | `CONVERSATIONS_TAKE` | assignee_user_id = actor; resetea unread; emite `CONVERSATION_TAKEN` |
| POST | `/{id}/release` | `CONVERSATIONS_RELEASE` | body `{to_assignee_type, to_bot_configuration_id?, reason?}`; emite `CONVERSATION_RELEASED` |
| POST | `/{id}/close` | `CONVERSATIONS_CLOSE` | status=closed, cierra log vigente |
| POST | `/{id}/reopen` | `CONVERSATIONS_TAKE` | valida no-otra-open (sino `CONVERSATION_ALREADY_OPEN` 409) |
| POST | `/{id}/mark-read` | `CONVERSATIONS_READ` | unread_count=0 |
| POST | `/me/conversations/list` | `MY_CONVERSATIONS_READ` | mi bandeja (assignee_user_id = actor). `PaginatedResponse[ConversationListItem]` |

> **Outbox en las acciones de handoff**: `take`/`release`/`close`/`reopen`/`mark-read` **se mantienen** (mismo response/permiso); además escriben un `message_outbox(op=conversation_upsert)` para reflejar `assignee_user_id`/`allowed_reader_ids`/`unread_count`/`status` en el doc espejo Firestore (mantiene las Security Rules y el inbox live al día).

> **`ALLOWED_FIELDS`** (lección hotfix `cd10c78` de staff): solo columnas reales de `conversation` (`status`, `assignee_type`, `assignee_user_id`, `channel_account_id`, `last_message_at`, `created_on`, `unread_count`). Los denormalizados (person `full_name`, channel `name`, assignee `full_name`, `last_message_preview`) **NO** son sortable/filterable server-side → la búsqueda por nombre/identificador es **client-side**; los deep-links por `*_id` se traducen a filtros en el repo. `defaultSort = last_message_at desc` (columna real; el prefetch del RSC y el `defaultSort` de la tabla DEBEN coincidir, sino footer desync + flash).

> **Códigos de error de dominio** (`detail` en **español**, `code` en inglés): `CHANNEL_ACCOUNT_NOT_FOUND` (404) · `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` (409) · `CHANNEL_CREDENTIALS_MISSING` (500) · `CONVERSATION_NOT_FOUND` (404) · `CONVERSATION_NOT_OPEN` (400) · `CONVERSATION_ALREADY_OPEN` (409) · `INVALID_ASSIGNEE` (400) · `NOT_CONVERSATION_ASSIGNEE` (403) · `MESSAGE_NOT_FOUND` (404) · `UNSUPPORTED_CONTENT_TYPE` (400) · `MESSAGE_SEND_FAILED` (interno; el endpoint devuelve 200 con el message fallido) · `WEBHOOK_SIGNATURE_INVALID` (403, en el router top-level). Los validators Pydantic van en inglés (el front re-valida con Zod). La tabla con el "cuándo" exacto está en [`backend.md`](backend.md).

## Permisos seed

12 permisos. Ya canónicos en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md) — **no se redefinen aquí, se referencian**. F0 los agrega a `SEED_PERMISSIONS`:

```
MENU-CONVERSATIONS ·
CHANNEL_ACCOUNTS_{READ,CREATE,UPDATE,DELETE} ·
CONVERSATIONS_{READ,TAKE,RELEASE,CLOSE} ·
MESSAGES_{READ,SEND} ·
MY_CONVERSATIONS_READ
```

**Roles seed que tocan `conversations`** (subsets canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md#matriz-roles--permisos)):

- `ADMIN` — **todos** los 12 permisos (incluye configurar canales).
- `ASESOR` — corazón de su trabajo: `MENU-CONVERSATIONS`, `CONVERSATIONS_{READ,TAKE,RELEASE,CLOSE}`, `MESSAGES_{READ,SEND}`, `MY_CONVERSATIONS_READ`. **NO** `CHANNEL_ACCOUNTS_*` (solo admin configura canales).
- `DOCTOR` — sin permisos en conversations.

> Los sets `ASESOR_PERMISSION_CODES` ya traen los códigos conversations en su forma canónica → se auto-expanden al agregar las perms (a prueba de orden de seed). `find_by_identifier_or_create` **no** tiene endpoint público (no hay permiso "el sistema crea contactos"); la invoca el webhook processor server-side con `created_by = SYSTEM`.

## Frontend (resumen)

UI 100% en español. Nav grupo **"Conversaciones"** (`MENU-CONVERSATIONS`):

- **"Bandeja"** (`/conversaciones/bandeja`, `CONVERSATIONS_READ`) — inbox global.
- **"Mi bandeja"** (`/conversaciones/mis-conversaciones`, `MY_CONVERSATIONS_READ`) — solo mías.
- **"Canales"** (`/conversaciones/canales`, `CHANNEL_ACCOUNTS_READ`) — CRUD de `ChannelAccount` (admin).

El **inbox** es la UI más pesada del módulo (como el timeline de crm / la grilla de staff): layout **2-paneles** (lista de conversaciones con filtros/chips/búsqueda client-side + URL state `nuqs`, a la izquierda; hilo de burbujas inbound/outbound/system + composer + controles de handoff, a la derecha), con **polling ~10s** (NO SSE/WebSocket — Cloud Run no los favorece con `min-instances 0` + cpu-throttling). Day-groups + "Hoy/Ayer" **client-only** (lección TZ recurrente — SSR en UTC desfasa el día en TZ negativas). Mutaciones de handoff hacen refetch local **y** `router.refresh()` (la conversación pinta datos denormalizados; lección crm F3). El detalle completo (mockups, estados, glosario, componentes Fluent) está en [`ui.md`](ui.md) y [`frontend.md`](frontend.md).

Glosario UI: Conversación · Mensaje · Canal · Bandeja · Tomar · Liberar · Cerrar · Reabrir · Asignado a · Sin asignar · Sin leer · Entregado · Leído · Enviado · Falló el envío · Reintentar.

## Decisiones de diseño (no obvias)

### Alcance MVP = WhatsApp in + out reales — [ADR-004](../../decisions/ADR-004-conversation-channel-account.md)

**Confirmado por usuario (2026-06-02).** El MVP cablea WhatsApp **entrante** (webhook real: GET verify + POST con validación de firma + parseo/persistencia) **y saliente** (envío real contra Meta WhatsApp Cloud API / Graph API), más la orquestación crm + inbox + handoff. WhatsApp = único canal del MVP; el modelo queda listo para Telegram/web/otros **sin migración** (enum + processor por canal). ADR-004 se **actualiza** en esta fase (sigue Accepted) con las decisiones refinadas y corrige una afirmación errónea sobre Secret Manager (ver ADR-010).

### Credenciales por-cuenta vía Secret Manager SDK en runtime (cacheado) — [ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md)

**Confirmado por usuario.** El template hoy inyecta secretos fijos por env (deploy-time, vía `--set-secrets` de Cloud Run → `SECRET_KEY`/DB-creds como env vars que la app lee por `Settings`, **sin SDK**). Las credenciales por-`ChannelAccount` necesitan resolución **dinámica** para operar multi-cuenta sin redeploy. Decisión: SDK `google-cloud-secret-manager` + `app/core/secrets.py` con cache TTL + fallback env (local/test). Alternativas rechazadas: inyección por env (1 número por deploy), columna cifrada en BD (secreto en backups). Patrón reusable por futuros módulos con secretos por-tenant/cuenta. **ADR-010 (nuevo, Accepted).**

### Auto-asignación al dueño del lead, con fallback a bandeja compartida

**Confirmado por usuario.** Al crear una conversación nueva para una Person, se asigna automáticamente al asesor de su `LeadAssignment` activo (el round-robin que ya hace crm, leído vía `advisor_map`); si la Person no tiene asesor → `unassigned` (bandeja compartida). El asesor puede reasignar/tomar igual. Continuidad "mis leads = mis chats" (aprovecha `/me/conversations` + `/me/leads`). La auto-asignación abre un `ConversationAssignmentLog` con `by_actor_user_id = NULL` (automático).

### Texto-primero; adjuntos modelados pero processing diferido (F4)

**Confirmado por usuario.** `MessageAttachment` se MODELA desde el inicio (tabla + enum `AttachmentType`, creada en la migración de threads F2 para no re-migrar), pero el processor de F2/F3 procesa **solo texto** (`content_type=text`; otros → `UNSUPPORTED_CONTENT_TYPE` 400 en outbound). El download/storage de media va en F4 (diferida); la decisión de storage (lazy proxy vs GCS) se re-confirma al llegar a F4.

### Mensajes y logs sin SoftDelete (audit inmutable)

Los **mensajes** (docs Firestore) y `ConversationAssignmentLog` **NO** se borran ni soft-deletean — la auditoría es honesta o no es (mismo criterio que `LeadStatusHistory`/`LeadActivity` de crm). Un mensaje enviado/recibido es un hecho; no se borra. Solo `ChannelAccount` y `Conversation` (datos de negocio vivos) llevan `SD`. `MessageOutbox` tampoco lleva `SD` (es cola operativa, no entidad de negocio).

### Persistencia de mensajes: Firestore (CQRS) — control plane Postgres + data plane Firestore

> **Decisión revisada (2026-06-03).** La versión previa de este README decía "mensajes en Postgres, no Firestore"; esa decisión se **revirtió**. Ahora: los **mensajes viven en Firestore**, con una arquitectura **CQRS** que NO rompe consistencia ni el modelo de seguridad del template. Documentado en [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md) (ADR-004 se revisa: `Message` ya no es entidad Postgres relacional).

El stream de mensajes se persiste en **Cloud Firestore** (Native mode), no en Postgres, separando responsabilidades:

- **Postgres = control plane / fuente de verdad** del estado relacional/operativo (`channel_account`, `conversation`, `conversation_assignment_log`, `message_outbox`). Acá viven las FKs (incl. la aditiva `lead_activity → conversation`), el `UNIQUE` 1-open y los filtros SQL del inbox.
- **Firestore = data plane / read-model real-time** del stream (proyección): `conversations/{cid}` (doc espejo) + `conversations/{cid}/messages/{mid}` (el mensaje). Es lo que el browser **lee en vivo** (listeners `onSnapshot`).
- **Transactional Outbox** (`message_outbox`) sincroniza Postgres→Firestore sin transacción distribuida ni pérdida: la escritura al outbox va **dentro de la TX** del control plane; un **relay** (BackgroundTasks MVP / Cloud Tasks prod) la espeja a Firestore con el Admin SDK (`set(doc_id=mid)` idempotente). **Postgres manda; Firestore es proyección eventual** (latencia ms–seg).
- **Seguridad — Custom Tokens + Security Rules** (no rompe "el browser no muta el backend / JWT server-side / RBAC"): el backend mintea un **custom token** de Firebase por `POST /conversations/realtime/token` (gated por `CONVERSATIONS_READ` o `MY_CONVERSATIONS_READ`, con `developer_claims = {scope:"conversations", is_advisor, can_read_all}`). El JWT/RBAC es la fuente de verdad de quién recibe token y con qué claims. El browser hace `signInWithCustomToken(...)` → ID token (1h) → abre listeners **READ-ONLY**. Las **Security Rules** (`firestore.rules`, versionadas en el repo, desplegadas por CI) espejan el RBAC vía `allowed_reader_ids` ([assignee] + admins/supervisores, mantenido por el backend vía `conversation_upsert` del outbox): `allow write: if false` para clientes (solo el Admin SDK escribe, que bypassa rules). **Todas las escrituras** (enviar, tomar, liberar) siguen 100% server-side (browser → Next server → backend → Meta + Firestore vía Admin SDK). Se preserva el principio del template: el browser solo **lee** el stream que está autorizado a ver.

**Por qué Firestore y por qué CQRS** (resumen — detalle en ADR-011): se eligió Firestore por su **real-time client sync** nativo para el thread del inbox (lo que el polling Postgres no da); CQRS (y no dual-store ingenuo) para no romper las FKs/queries relacionales del control plane ni el modelo de seguridad server-side. **Audit/analítica** de mensajes = export Firestore→BigQuery (nativo GCP), no Postgres. **Binarios de media** (imágenes/audio/docs): NO van a Firestore; van a **object storage (GCS)** en **F4** (adjuntos, diferida), y el `attachments: [{type, url(GCS firmada), ...}]` del doc del mensaje apunta ahí. (En el MVP texto-primero aún no hay media.)

### Idempotencia: outbox-unique + doc-id

La deduplicación ante reenvío de webhook de Meta (o reintento outbound) es **doble**, y reemplaza el `UNIQUE` parcial `(conversation_id, external_id)` que tenía la tabla `message`:

- **`message_outbox.id` UNIQUE = mid** (`wamid` inbound / uuid outbound) → `INSERT ... ON CONFLICT (id) DO NOTHING`. Dedup real en la TX Postgres; el `unread_count++` y el `conversation_upsert` solo corren si el insert fue **nuevo**.
- **doc-id = mid en Firestore** → el relay hace `set(doc_id=mid)` (create-if-absent idempotente). Si el relay corre dos veces, el doc no se duplica.

Doble dedup → el mismo `wamid` no produce dos mensajes ni infla el `unread_count`, incluso bajo webhooks concurrentes (sumado al advisory lock de `find_by_identifier_or_create`).

### FK forward a módulos futuros — [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md)

`bot_configuration_id` (en `ChannelAccount`/`Conversation` Postgres y en el doc del mensaje en Firestore) y `default_campaign_id` (en `ChannelAccount`) apuntan a `bots` (#6) y `marketing` (#8), que **no existen todavía** → `varchar(36)` nullable **sin** `ForeignKey` ni `relationship` en Postgres (una FK a tabla inexistente rompería la migración; un `relationship` a clase inexistente rompería el mapper al importar); campo libre en el doc Firestore. La FK constraint la agregará aditivamente el módulo dueño cuando cree su tabla. Hoy estas columnas son SIEMPRE NULL. Recíprocamente, conversations **es** el dueño de `lead_activity.related_conversation_id` y agrega su FK aditiva en F2 (ver [Enganche §4](#4-fk-forward-lead_activityrelated_conversation_id-conversations-es-el-dueño)).

### Defaults aplicados (no se preguntaron; corregibles)

- **Thread en vivo = Firestore real-time** (listeners `onSnapshot`, read-only); el **listado** del inbox = polling Postgres ~10s (NO SSE/WebSocket — Cloud Run no los favorece con `min-instances 0` + cpu-throttling). El real-time del thread lo da Firestore, no SSE.
- **Webhook entrante = TX Postgres síncrona** antes del 200 (rápido; sin bot que genere auto-reply lento) + relay a Firestore aparte (`BackgroundTasks`). Cola durable (Cloud Tasks) / `--no-cpu-throttling` diferido a bots.
- **Contacto desconocido** → `PersonCreate(first_name=pushname.trim()[:80] o "Contacto", last_name="(WhatsApp)", identifiers=[])` (placeholder editable).
- **Outbound fallido** → escribe el doc Firestore igual (`failed_at`/`failure_reason`/`external_status: failed`), endpoint devuelve **200** con el message fallido (UI reintenta), NO 502.
- **Emisión a la timeline de crm**: SOLO `CONVERSATION_TAKEN`/`RELEASED` (no `MESSAGE_SENT` por-mensaje).

## Implementación por fases

Una fase por grupo cohesivo. Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist mapeado a estas fases. Migraciones revid ≤ 32 chars (límite `alembic_version varchar(32)`; clinic F3 reventó con 34).

| Fase | Alcance | Migración (revid ≤32) |
|---|---|---|
| **F0 — Prep** | 12 perms CONVERSATIONS → `SEED_PERMISSIONS` (ya canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md)) + asignar a ADMIN/ASESOR (auto-expand); nav grupo "Conversaciones" + iconos; `endpoints.ts` (bloque conversations + webhooks N/A front); `types/conversations.types.ts` (espejo completo, inerte); skeleton backend inerte (`models/schemas/repositories/services/routers/__init__.py` con docstrings). **NO** registrar en `app/modules/__init__.py` ni `main.py` (lo cablea F1). | ninguna (solo seed) |
| **F1 — ChannelAccount + secret_resolver + Firebase Admin bootstrap** | tabla `channel_account` (UNIQUE parcial dialect-agnóstico); backend CRUD + `app/core/secrets.py` (SDK + cache TTL + fallback) + `channel_account.get_credentials` + **`app/core/firestore.py`** (Firebase Admin SDK init ADC + `mint_custom_token`); registrar `conversations` en `app/modules/__init__.py` + aggregator router en `main.py`; deps `google-cloud-secret-manager` + **`firebase-admin`** en pyproject; **provisionar Firestore** (detectar/crear DB Native mode qa+prod; desplegar `firestore.rules` base) + roles IAM de la SA (`datastore.user` + `serviceAccountTokenCreator`); UI `/conversaciones/canales`. (Sin webhooks/mensajes aún.) **El endpoint `realtime/token` puede ir en F1 o F2.** | `0015_conv_channel_account` (25) ✓; down_revision `0014_crm_customer_lifecycle` |
| **F2 — Inbound pipe (control-plane + Firestore data-plane)** | `conversation` + `conversation_assignment_log` + **`message_outbox`** (UNIQUE parciales dialect-agnósticos; `payload` JSONB) + **FK aditiva** `lead_activity.related_conversation_id → conversation.id` — **NO** crea `message`/`message_attachment` tables; webhook router top-level (`app/routers/webhooks.py`) GET verify + POST inbound (firma) + `webhook_processor/whatsapp.py` (parse + `find_or_create_open` + **TX Postgres + outbox**) + **relay a Firestore** (docs `conversations/{cid}` + `messages/{mid}` vía Admin SDK) + **crm hardening** (advisory lock) + auto-asignación al dueño del lead + `firestore.rules` con `allowed_reader_ids`; inbox listing + detail (listado por polling Postgres) + **thread con `onSnapshot` real-time** (read-only) + `getRealtimeToken` action + `lib/firebase/client.ts`; UI inbox 2-paneles (recibir + ver). Sin outbound aún. | `0016_conv_threads` (17) ✓; down_revision `0015_conv_channel_account` |
| **F3 — Handoff + outbound** | take/release/close/reopen + `ConversationAssignmentLog` writes + `conversation_upsert` al outbox (refleja `assignee`/`allowed_reader_ids`) + **crm `lead_activity.log` extendido** (`related_conversation_id`) + emisión `CONVERSATION_TAKEN/RELEASED` + outbound send real (Meta Graph API + escritura/estados `delivered`/`read` en vivo en el doc Firestore vía Admin SDK) + composer UI + `/me/conversations`. Completa el human-inbox MVP. | ninguna (tablas ya existen) |
| **F4 — Adjuntos/media (DIFERIDA)** | binarios → **GCS** (igual que antes); el doc Firestore del mensaje lleva `attachments: [{type, url(GCS firmada), mime, ...}]`; inbound/outbound media + render UI. Texto-primero en F2/F3. Fuera del MVP inicial. | (a definir en F4) |

> Flujo de cada fase = el de la metodología: leer fichas → backend e2e + smoke (sqlite create_all, RESULT=PASS + conteo a stdout) → frontend e2e (subagente contexto fresco) → tsc + build → review adversaria (Workflow 4 dims → verificación por hallazgo) → commit limpio (sin Co-Authored-By) → ff develop→qa → QA E2E con limpieza → **gate de usuario (AskUserQuestion separado del merge)** → prod → PROD read-only → actualizar memoria. Backend venv: `backend/.venv/Scripts/{python,ruff,mypy}.exe`.

## Reconciliaciones post-fichas (autoritativo — NO re-litigar)

Resoluciones de los supuestos que las 4 fichas dejaron abiertos o asumieron distinto. **Este README gana**; al implementar, alinear `backend.md`/`ui.md`/`frontend.md` a esto.

1. **Mensajes de sistema en el hilo (handoff)** — el MVP **NO** inserta un `Message(sender_type=system, content_type=system_notification)` por tomar/liberar/cerrar/reabrir. El handoff se ve en el hilo vía el `assignment_history` (`ConversationAssignmentLog`) en el **header del hilo** (popover/accordion) + el badge **"Asignado a X"**. Los valores de enum `SenderType.system` / `ContentType.system_notification` quedan **reservados** (forward, no se emiten en el MVP). (Reconcilia `ui.md`, que dibuja burbujas de sistema como opción, y `frontend.md`, que documentó ambos caminos: gana el de `assignment_history`, sin burbuja de sistema en MVP.)
2. **`response_model` de las acciones de handoff** (`take`/`release`/`close`/`reopen`/`mark-read`) = **`SingleResponse[ConversationDetail]`** → el front hace `setDetail(data)` + `router.refresh()` (lección crm F3). (Reconcilia el supuesto de `frontend.md`.)
3. **Orden del hilo (Firestore)** — los mensajes ya **no son tabla Postgres** (viven en `conversations/{cid}/messages/{mid}`), así que **no hay `ALLOWED_FIELDS` de `message`**. El hilo ordena por **`created_at asc`** (cronológico natural) vía el `orderBy('created_at')` del `onSnapshot` del cliente Firestore (path primario) y del `/messages/list` fallback (Admin SDK server-side). Complementa el `ALLOWED_FIELDS` de `conversation` ya fijado arriba (ese sí sigue siendo SQL). (Reconcilia el gap de `frontend.md`.)
4. **Denormalización de `ConversationListItem.person`** = shape `crm.schemas.person.PersonOption` (`{id, full_name, document_number, primary_identifier}`), poblado vía un **helper aditivo** `crm.person_repository.person_option_map(person_ids)` (se agrega en F2; patrón aditivo idéntico a `staff branch_repository.get_by_ids` y a los batch maps de crm — **sin** N+1, **sin** relationship cross-módulo). (Reconcilia el gap de `backend.md`/`frontend.md`; el nombre tentativo `ConversationPersonRef` del front = `PersonOption`.)
5. **Flag "configurado" en `ChannelAccountItem`/`Detail`** = `credentials_configured: bool` (derivado server-side de si `secret_name`/env resuelven; **el secreto NUNCA viaja al schema**). (Fija el nombre que `frontend.md` dejó tentativo.)
6. **Destinatario del outbound (`to` de Meta)** = el identificador **WhatsApp principal** de la `Person` (la conversación tiene `person_id` → se lee su `primary_identifier` de canal `whatsapp` vía crm en F3). **Sin** columna nueva en conversations. (Reconcilia el gap de `backend.md`.)
7. **`CHANNEL_CREDENTIALS_MISSING` = 500** (mala configuración del operador). En el **outbound NO se levanta** (se escribe el doc Firestore del mensaje en estado fallido y se devuelve 200); aplica en el webhook (firma) y en `get_credentials` cuando no hay secreto ni fallback. (Reconcilia la doble mención 400/500 entre §6/§9 de la spec → canónico **500**.)
8. **`release` con `to_assignee_type=advisor`** → `INVALID_ASSIGNEE` (400) (para asignar a un asesor se usa `take`). En el MVP `release` solo ofrece **`unassigned`** (bots no existe → no hay `bot`; advisor-a-otro-asesor diferido). (Reconcilia `backend.md`/`frontend.md`.)
9. **Trigger de `mark-read`** = automático al seleccionar una conversación con `unread_count>0` **+** botón explícito "Marcar como leída". (Reconcilia el gap UX de `ui.md`/`frontend.md`.)
10. **Reintento de outbound fallido** = un mensaje **nuevo** (re-`POST /{id}/messages` con el mismo `content` → `mid` uuid nuevo); el doc Firestore del mensaje fallido queda **inmutable**. NO hay endpoint de "re-send sobre el mismo message". (Reconcilia `ui.md`.)
11. **Versión de Graph API + `httpx`** — fijar una versión concreta de la Graph API al implementar F3 (la vigente, ej. `v21.0`), parametrizada como `v<ver>` en los docs. `httpx` se **promueve a dependencia de runtime** en `pyproject.toml` (hoy puede estar solo en deps de test) para el envío a Meta.
12. **`secret_resolver`** — usar el cliente **async** del SDK si la versión instalada lo expone; si no, llamada **sync en threadpool**. Settings nuevos para el fallback env (defaults vacíos): `GCP_PROJECT_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`. Cliente SDK **lazy** (no al import) para no romper el boot sin GCP (smoke/local).
13. **Migración — `sqlite_where` compuesto** — el UNIQUE parcial de `conversation` usa `WHERE status='open' AND deleted_at IS NULL` (condición **compuesta** con literal de string). El precedente crm (`lead_assignment`) solo usó `deleted_at IS NULL`. **Validar en el smoke de F2** que sqlite acepta el `sqlite_where` compuesto; si no, además se valida "una sola open" en el service (guard `CONVERSATION_ALREADY_OPEN`). La migración Postgres usa `postgresql_where` (patrón shipped en crm).
14. **Rediseño CQRS — mensajes en Firestore (2026-06-03)** — SUPERSEDE la persistencia de mensajes que asumían las 4 fichas (Postgres `message`/`message_attachment` relacionales). Ahora: mensajes en **Firestore** (data plane real-time), control plane Postgres (`channel_account`/`conversation`/`conversation_assignment_log`/`message_outbox`), **Transactional Outbox** para el sync, **Custom Tokens + Security Rules** para la lectura real-time del browser. Documentado en **[ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md)** (Accepted); **[ADR-004](../../decisions/ADR-004-conversation-channel-account.md) se revisa** (Message ya no es entidad Postgres). Ver [Entidades](#entidades) + [Persistencia de mensajes](#persistencia-de-mensajes-firestore-cqrs--control-plane-postgres--data-plane-firestore) + [Idempotencia](#idempotencia-outbox-unique--doc-id). **NO** cambian: crm engagement, ChannelAccount, las 4 decisiones de negocio, los 12 permisos, webhook síncrono, polling del **listado** (solo el thread pasa a real-time), UI 100% español, `PUT`, revid ≤32.

## Diagramas

- ER: [`docs/diagrams/er-conversations.puml`](../../diagrams/er-conversations.puml)
- Class diagram (modelos + repos + services + secret_resolver + webhook_processor): [`docs/diagrams/class-backend-conversations.puml`](../../diagrams/class-backend-conversations.puml)

> Ambos diagramas se **(re)generan al modelo de esta spec** en la consolidación post-fichas (lo hace el implementador): **ER** = las 4 tablas Postgres (`channel_account`/`conversation`/`conversation_assignment_log`/**`message_outbox`**) — **quitar `message`/`message_attachment`** — + Firestore como store externo (`<<external, Firestore>>`) con `conversations/{cid}` + `.../messages/{mid}` y la relación `conversation 1—projection→ firestore doc`; mantener la FK aditiva `lead_activity → conversation`. **Class** = agregar `app/core/firestore.py` (Admin SDK), `message_outbox` model + repo, el relay, el `realtime` router; `message.py` service habla con Firestore (Admin SDK) + outbox; **quitar** los modelos `Message`/`MessageAttachment` Postgres (pasan a "Firestore docs" anotados). Anotar `channel_type = reuse crm.ChannelType`; `bot_configuration_id`/`default_campaign_id` = forward sin constraint (ADR-009); `secret_resolver` + Firebase Admin SDK en `app.core`; el `webhook_processor` y los helpers crm consumidos (`find_by_identifier_or_create`, `lead_activity.log`, `advisor_map`). Usar `PUT` (no `PATCH`) en toda referencia.

## Próximos pasos / TODOs deliberados

- [ ] **Consolidación post-fichas** (la hace el implementador): actualizar [ADR-004](../../decisions/ADR-004-conversation-channel-account.md) (Accepted, "act. 2026-06-03": corregir Secret Manager, PATCH→PUT, decisiones refinadas, **Message ya no es entidad Postgres → ver ADR-011**) + crear [ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md) (Accepted) + **crear [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md)** (Accepted, "Stream de mensajes en Firestore (CQRS) — control plane Postgres + data plane Firestore + Transactional Outbox + Custom-Token auth"); regenerar `er-conversations.puml` + `class-backend-conversations.puml` al modelo CQRS; borrar el overview viejo `docs/modules/conversations.md` y repuntar TODOS sus links (`grep "modules/conversations.md"`) a este README; crear `project_medisage_conversations_plan.md` + puntero en MEMORY.md.
- [ ] **FK aditivas** de módulos futuros sobre conversations: `bots` (#6) → FK + relationship a `channel_account.bot_configuration_id`, `conversation.bot_configuration_id` (Postgres); el `bot_configuration_id` del mensaje vive en el doc Firestore (campo libre, sin FK); `marketing` (#8) → FK a `channel_account.default_campaign_id`. Documentarlo como TODO en los overviews de esos módulos al diseñarlos.
- [ ] **Provisionar Firestore** (F1): detectar/crear la DB Native mode por entorno (`medisage-qa`/`medisage`, location `us-central1`) + desplegar `firestore.rules` (CI) + roles IAM de la SA (`datastore.user` + `serviceAccountTokenCreator`) + dep `firebase-admin`; config pública `NEXT_PUBLIC_FIREBASE_*` + dep `firebase` (Web SDK) en el frontend.
- [ ] **F4 (adjuntos/media)**: re-confirmar storage (lazy proxy vs GCS) y cablear download/upload de media + render UI.
- [ ] **Cuando `bots` agregue auto-reply lento**: mover el webhook a procesamiento asíncrono (cola / `BackgroundTasks` + `--no-cpu-throttling --min-instances 1`) y considerar SSE/WebSocket para el inbox en vivo (hoy polling).
- [ ] **Crear los secretos por env** (`medisage-whatsapp-*-{qa,prod}`) en Secret Manager al desplegar F1/F2 (la SA de Cloud Run ya tiene `secretAccessor`).
