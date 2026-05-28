# Módulo `conversations`

> **Última actualización**: 2026-05-28
> **Propósito**: mensajería multicanal — cuentas de canal, conversaciones, mensajes, attachments y historial de handoff bot↔asesor.
> **Path del código**: `backend/app/modules/conversations/`

## Resumen

`conversations` es el **dueño del pipe de mensajería**. Recibe los mensajes inbound desde los webhooks de los proveedores (WhatsApp Cloud API, Telegram Bot API, etc.), los persiste, identifica el `Person` correspondiente vía `crm.PersonContactIdentifier` y emite eventos para que `bots` (si está activo) o el asesor responda.

```
┌────────────────────┐     POST            ┌────────────────────────────┐
│ Provider (Meta /  │ ────────────────────▶│ /api/v1/webhooks/whatsapp/ │
│  Telegram / ...)   │   (firma verificada) │   {channel_account_id}     │
└────────────────────┘                      └────────────┬───────────────┘
                                                         │ delega
                                                         ▼
                                          ┌──────────────────────────────┐
                                          │ conversations.services       │
                                          │   .webhook_processor         │
                                          └──────────────┬───────────────┘
                                                         │ orquesta
                                  ┌──────────────────────┼──────────────────────┐
                                  ▼                      ▼                      ▼
                            ┌─────────┐           ┌─────────┐             ┌─────────┐
                            │   crm   │           │  bots   │             │  msgs   │
                            │ match   │           │ decide  │             │ persist │
                            │ Person  │           │ respond │             │         │
                            └─────────┘           └─────────┘             └─────────┘
```

Sobre el handoff:

- Cada `Conversation` tiene un `assignee_type ∈ {bot, advisor, unassigned}` + `assignee_user_id?`.
- Cuando un asesor "toma" la conversación, se actualiza el `assignee` y se cierra el `ConversationAssignmentLog` previo (`ended_at = now()`) + se abre uno nuevo.
- El bot consulta `Conversation.assignee_type` antes de responder — si es `advisor`, **no responde**, solo persiste el mensaje entrante.

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `ChannelAccount` | `channel_account` | Cuenta de canal de la clínica: tipo, identificador externo, secret reference, bot por defecto. |
| `Conversation` | `conversation` | Hilo activo o cerrado entre una Person y una ChannelAccount. |
| `Message` | `message` | Cada mensaje individual (inbound u outbound). |
| `MessageAttachment` | `message_attachment` | Adjuntos del mensaje (imagen, audio, doc, location, sticker, contact_card). |
| `ConversationAssignmentLog` | `conversation_assignment_log` | Historial de handoff (bot→advisor→bot→...). |

### `ChannelAccount`

Cuenta de canal que opera la clínica. Una clínica puede tener varias cuentas del mismo canal (ej. 2 números WhatsApp Business para verticales distintas).

- `channel_type: varchar(40)` — enum cerrado en código: `whatsapp / telegram / web / instagram / facebook / phone / email`. Cruza con `crm.PersonContactIdentifier.channel_type`.
- `name: varchar(120)` — nombre humano ("WhatsApp Estética", "WhatsApp Dental").
- `external_identifier: varchar(255)` — identificador del proveedor: número WhatsApp Business (`+51999111222`), username del bot Telegram, etc.
- `secret_name: varchar(255)` `<<nullable>>` — **nombre del secret en GCP Secret Manager** que guarda credentials sensibles (access token, app secret). El código lo lee en runtime vía `google-cloud-secret-manager` (ya en stack del template). Nullable porque algunos canales no requieren credencial (ej. canal "phone" para llamadas registradas a mano).
- `webhook_verify_token: varchar(255)` `<<nullable>>` — challenge string que el provider envía para verificar el endpoint (Meta lo requiere en GET). No es secreto en sí (lo envía el provider y lo comparamos); se guarda aquí.
- `bot_configuration_id: varchar(36)` `<<nullable, FK→bot_configuration>>` — qué bot atiende este canal por defecto. `NULL` = sin bot asignado, las conversations entran como `unassigned`.
- `default_campaign_id: varchar(36)` `<<nullable, FK→campaign>>` — campaña de atribución para leads que entran por este canal. Marketing puede tener una campaña "Tráfico orgánico WhatsApp" o no asignar nada.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.
- **UNIQUE `(channel_type, external_identifier)` WHERE `deleted_at IS NULL`** — el mismo número no puede pertenecer a dos cuentas vivas.

### `Conversation`

Hilo de mensajería entre una `Person` y una `ChannelAccount`. **Múltiples conversations por (person, channel_account) son posibles a lo largo del tiempo, pero solo una puede estar `open` simultáneamente**. Confirmado por usuario.

- `channel_account_id: varchar(36)` `<<FK→channel_account>>`.
- `person_id: varchar(36)` `<<nullable, FK→person>>` — `NULL` solo entre que llega el primer mensaje y `crm.person.find_by_identifier_or_create` resuelve (ventana corta, mismo request). En la práctica casi siempre poblado.
- `status: varchar(20)` — `open / closed`. Enum cerrado.
- `assignee_type: varchar(20)` — `bot / advisor / unassigned`.
- `assignee_user_id: varchar(36)` `<<nullable, FK→user>>` — `NULL` si `assignee_type ∈ {bot, unassigned}`. Si `assignee_type = advisor`, requerido.
- `bot_configuration_id: varchar(36)` `<<nullable, FK→bot_configuration>>` — qué bot está atendiendo (puede diferir del default del channel_account, ej. si se decide preventa/postventa al matchear Person).
- `opened_at: timestamptz` — cuándo se abrió.
- `closed_at: timestamptz` `<<nullable>>`.
- `last_message_at: timestamptz` `<<nullable>>` — denormalizado para sort y listado de inbox.
- `last_message_preview: varchar(255)` `<<nullable>>` — primeros 255 chars del último mensaje, para inbox UI.
- `unread_count: int` `default 0` — incrementa con cada inbound, se resetea cuando el asesor abre la conversación o el bot la marca leída.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.
- **UNIQUE partial**: `(person_id, channel_account_id)` WHERE `status = 'open' AND deleted_at IS NULL` — garantiza una sola conversation activa por par. Requiere `person_id NOT NULL` en el index (Postgres lo permite con `WHERE person_id IS NOT NULL` añadido si quisiéramos hilar más fino; en práctica, no se cierra conversación sin person resuelto).

**Reglas de invariante** (validadas en service):
- `assignee_type = advisor` ⇒ `assignee_user_id NOT NULL`.
- `assignee_type ∈ {bot, unassigned}` ⇒ `assignee_user_id IS NULL`.
- `assignee_type = bot` ⇒ `bot_configuration_id NOT NULL`.
- Cerrar una conversation (`status = closed`) cierra también el `ConversationAssignmentLog` actual (`ended_at = now()`).
- Reasignar (cambio de assignee) cierra el log actual e inserta uno nuevo en la misma transacción.

### `Message`

Cada mensaje individual.

- `conversation_id: varchar(36)` `<<FK→conversation>>`.
- `direction: varchar(10)` — `inbound / outbound`.
- `sender_type: varchar(20)` — `contact / bot / advisor / system`. (`system` para notas internas tipo "Asesor X tomó la conversación", visible en el timeline UI.)
- `sender_user_id: varchar(36)` `<<nullable, FK→user>>` — `NULL` si `sender_type ∈ {contact, bot, system}`. Si `advisor`, requerido.
- `bot_configuration_id: varchar(36)` `<<nullable, FK→bot_configuration>>` — si fue enviado por bot, qué bot.
- `content_type: varchar(20)` — `text / image / audio / video / document / location / sticker / contact_card / system_notification`. Cruza con `MessageAttachment.attachment_type` cuando aplique.
- `content: text` `<<nullable>>` — texto del mensaje, o transcripción de audio si el proveedor la trae, o el cuerpo del system_notification.
- `external_id: varchar(255)` `<<nullable>>` — id del mensaje en el proveedor (WhatsApp `wa_id`, Telegram `message_id`).
- `external_status: varchar(40)` `<<nullable>>` — último estado del proveedor (`sent / delivered / read / failed`).
- `sent_at: timestamptz` — cuándo lo envió/recibió el provider.
- `delivered_at: timestamptz` `<<nullable>>` — cuando el provider confirmó delivery.
- `read_at: timestamptz` `<<nullable>>` — cuando el provider confirmó read.
- `failed_at: timestamptz` `<<nullable>>` — cuando falló envío.
- `failure_reason: varchar(255)` `<<nullable>>`.
- `provider_payload: jsonb` `<<nullable>>` — payload original del proveedor (debugging).
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — mensajes no se borran (audit trail, también requerido por compliance de algunos proveedores).
- **UNIQUE partial**: `(conversation_id, external_id)` WHERE `external_id IS NOT NULL` — idempotencia: si el webhook reenvía el mismo evento (Meta lo hace ante errores), se detecta y se ignora.

### `MessageAttachment`

Adjunto de un mensaje. **1:N desde Message** — un mensaje puede traer múltiples adjuntos (en práctica WhatsApp manda 0 o 1, pero el modelo no se ata).

- `message_id: varchar(36)` `<<FK→message>>`.
- `attachment_type: varchar(20)` — `image / audio / video / document / location / sticker / contact_card`.
- `url: varchar(1000)` `<<nullable>>` — URL pública o firmada del archivo. `NULL` cuando es `location` (no aplica).
- `mime_type: varchar(100)` `<<nullable>>`.
- `size_bytes: int` `<<nullable>>`.
- `duration_sec: int` `<<nullable>>` — audio/video.
- `latitude: numeric(9,6)` `<<nullable>>` — location.
- `longitude: numeric(9,6)` `<<nullable>>` — location.
- `address_label: varchar(255)` `<<nullable>>` — location (texto descriptivo, si lo manda el provider).
- `original_filename: varchar(255)` `<<nullable>>`.
- `external_media_id: varchar(255)` `<<nullable>>` — id del medio en el proveedor (WhatsApp `media_id`). Para descargar bajo demanda en lugar de pre-descargar.
- `metadata: jsonb` `<<nullable>>` — campos específicos del proveedor.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — coherente con `Message`.

**Almacenamiento de archivos**: el módulo `conversations` **no decide** dónde se guardan los binarios. Decisión postergada (probable: GCS bucket en el proyecto GCP de medisage, URL firmada). El campo `url` apunta a donde sea que vivan. El service descarga del proveedor + sube a GCS al recibir inbound; al enviar outbound, sube el archivo a GCS primero y luego pasa la URL al provider.

### `ConversationAssignmentLog`

Historial inmutable de handoffs. Cada cambio de `(assignee_type, assignee_user_id)` cierra la fila actual y abre una nueva.

- `conversation_id: varchar(36)` `<<FK→conversation>>`.
- `from_assignee_type: varchar(20)` `<<nullable>>` — `NULL` en el primer log de la conversation.
- `from_assignee_user_id: varchar(36)` `<<nullable, FK→user>>`.
- `to_assignee_type: varchar(20)` — siguiente assignee.
- `to_assignee_user_id: varchar(36)` `<<nullable, FK→user>>`.
- `started_at: timestamptz`.
- `ended_at: timestamptz` `<<nullable>>` — `NULL` mientras esté vigente.
- `by_actor_user_id: varchar(36)` `<<nullable, FK→user>>` — quién hizo el handoff; `NULL` si fue automático (sistema/bot).
- `reason: varchar(255)` `<<nullable>>`.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`**.

## Esquemas (Pydantic v2)

Variantes habituales (`Create / Update / Item / Detail / Option`). Específicos del módulo:

- `ConversationListItem` lleva `person: PersonOption?`, `channel_account: ChannelAccountOption`, `assignee_user: UserAuditInfo?`, `last_message_preview`, `unread_count`. Optimizado para inbox.
- `ConversationDetail` extiende con `assignment_history: list[ConversationAssignmentLogItem]`.
- `MessageItem` lleva attachments inline (`attachments: list[MessageAttachmentItem]`).
- `MessageSendRequest { content?, content_type, attachments?: list[MessageAttachmentInput] }` — body del POST para enviar outbound.
- `TakeConversationRequest { reason? }` — el asesor pide tomar; service valida.
- `ReleaseConversationRequest { to_assignee_type, to_bot_configuration_id?, reason? }` — el asesor devuelve al bot o desasigna.

## Endpoints

### Bajo `/api/v1/conversations/`

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/channel-accounts/list` | `CHANNEL_ACCOUNTS_READ` |
| `POST` | `/channel-accounts` | `CHANNEL_ACCOUNTS_CREATE` |
| `GET` | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_READ` |
| `PATCH` | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_UPDATE` |
| `DELETE` | `/channel-accounts/{id}` | `CHANNEL_ACCOUNTS_DELETE` |
| `POST` | `/list` | `CONVERSATIONS_READ` | listado de conversations (inbox) |
| `GET` | `/{id}` | `CONVERSATIONS_READ` | detalle con assignment_history |
| `POST` | `/{id}/take` | `CONVERSATIONS_TAKE` | asesor toma (assignee_user_id = CurrentAuth.user.id) |
| `POST` | `/{id}/release` | `CONVERSATIONS_RELEASE` | devolver a bot o unassigned |
| `POST` | `/{id}/close` | `CONVERSATIONS_CLOSE` | cerrar conversation (status = closed) |
| `POST` | `/{id}/reopen` | `CONVERSATIONS_TAKE` | reabrir conversation cerrada (si pasa rule de unique-open) |
| `POST` | `/{id}/mark-read` | `CONVERSATIONS_READ` | resetea unread_count |
| `POST` | `/{id}/messages/list` | `MESSAGES_READ` | listado paginado de mensajes |
| `POST` | `/{id}/messages` | `MESSAGES_SEND` | enviar outbound (asesor o admin) |
| `GET` | `/me/inbox` | `MY_CONVERSATIONS_READ` | conversations asignadas al asesor logueado |

### Webhooks (top-level, fuera de `/api/v1/conversations/`)

Confirmado por usuario: el endpoint vive **top-level** para separar el ingress de provider externo de la API autenticada. No requiere JWT; valida firma del provider.

| Método | Ruta | Auth | Propósito |
|---|---|---|---|
| `GET` | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT, valida `hub.verify_token` contra `ChannelAccount.webhook_verify_token` | Meta verification challenge |
| `POST` | `/api/v1/webhooks/whatsapp/{channel_account_id}` | sin JWT, valida `X-Hub-Signature-256` con app_secret del channel | recepción de mensajes/status |
| `POST` | `/api/v1/webhooks/telegram/{channel_account_id}` | sin JWT, valida secret token en header `X-Telegram-Bot-Api-Secret-Token` | recepción Telegram |

**Estructura de código**:
- Routers webhook en `app/routers/webhooks.py` (top-level, no en `modules/`).
- Lógica de procesamiento en `app/modules/conversations/services/webhook_processor.py` con un módulo por proveedor:
  - `whatsapp.py:process_inbound(payload, channel_account, db) → list[Message]`
  - `telegram.py:process_inbound(payload, channel_account, db) → list[Message]`
- Los routers webhook delegan al processor. Mantiene la lógica donde vive el modelo.

## Permisos seed

```python
# Module: conversations
("MENU-CONVERSATIONS", "Ver menú conversaciones", "Bandeja de conversaciones", "conversations"),
("CHANNEL_ACCOUNTS_READ", "Ver canales", "Listar cuentas de canal", "conversations"),
("CHANNEL_ACCOUNTS_CREATE", "Crear canales", "Configurar nueva cuenta de canal", "conversations"),
("CHANNEL_ACCOUNTS_UPDATE", "Editar canales", "Editar configuración de cuenta de canal", "conversations"),
("CHANNEL_ACCOUNTS_DELETE", "Eliminar canales", "Soft-delete de cuenta de canal", "conversations"),
("CONVERSATIONS_READ", "Ver conversaciones", "Consultar conversaciones (bandeja global)", "conversations"),
("CONVERSATIONS_TAKE", "Tomar conversación", "Asumir conversación (handoff bot→asesor)", "conversations"),
("CONVERSATIONS_RELEASE", "Liberar conversación", "Devolver al bot o desasignar", "conversations"),
("CONVERSATIONS_CLOSE", "Cerrar conversación", "Marcar conversación como cerrada", "conversations"),
("MESSAGES_READ", "Ver mensajes", "Consultar mensajes de una conversación", "conversations"),
("MESSAGES_SEND", "Enviar mensajes", "Enviar mensajes outbound", "conversations"),
("MY_CONVERSATIONS_READ", "Ver mis conversaciones", "Ver mi bandeja personal asignada", "conversations"),
```

**Roles seed que tocan `conversations`**:
- `ADMIN` — todos.
- `ASESOR` — `MENU-CONVERSATIONS`, `CONVERSATIONS_{READ,TAKE,RELEASE,CLOSE}`, `MESSAGES_{READ,SEND}`, `MY_CONVERSATIONS_READ`. **No** edita ChannelAccounts.
- `DOCTOR` — sin permisos en este módulo (no usa conversations).

## Decisiones de diseño

### `Conversation + ChannelAccount` (multicanal con multi-cuenta por canal)
Documentado en [ADR-004](../decisions/ADR-004-conversation-channel-account.md).

### Credenciales en GCP Secret Manager, no en BD
Confirmado por usuario. `ChannelAccount.secret_name` es solo un puntero. El service `channel_account.get_credentials(channel_account)` resuelve el secret en runtime. Trade-off: dependencia operativa de Secret Manager (no se puede correr local sin mock); a cambio: rotación gratis, sin secretos en backups de BD, sin riesgo de leak en logs.

### Múltiples conversations por (person, channel_account) pero **única `open` simultánea**
Confirmado por usuario. La regla se mantiene con **partial UNIQUE index** sobre `(person_id, channel_account_id)` WHERE `status='open' AND deleted_at IS NULL`. Cuando se cierra una conversation, queda en BD para historial; si llega nuevo mensaje del mismo person/channel, se crea **una nueva**. Si el asesor quiere reabrir una vieja, el endpoint `/reopen` valida que no haya otra `open` y la reactiva (o falla con `BadRequestException`).

### Webhooks top-level, no dentro de `conversations`
Confirmado por usuario. Separar ingress externo (sin JWT, con firma) de la API autenticada hace que las concerns de auth no se mezclen. Los routers viven en `app/routers/webhooks.py`. La lógica de procesamiento sigue en `conversations.services.webhook_processor` para mantener cohesión por dominio.

### `MessageAttachment` estructurado en lugar de JSONB
Confirmado por usuario. Permite reportes rápidos ("cuántos audios envió el bot esta semana") y queries sobre tipos sin parsear JSONB. Costa una tabla más, pero los attachments son ciudadanos de primera clase del dominio (UI los renderiza distinto, audit los rastrea).

### `Message` y `ConversationAssignmentLog` sin SoftDelete
Coherente con el patrón de `crm.LeadStatusHistory` / `LeadActivity`: tablas de timeline / log inmutables son audit trail.

### `external_id` con UNIQUE partial para idempotencia
Meta WhatsApp Cloud API reenvía webhooks ante errores 5xx del backend. UNIQUE `(conversation_id, external_id)` WHERE `external_id IS NOT NULL` evita duplicar mensajes ante reintentos. Coherente con la documentación de Meta.

### `Conversation.bot_configuration_id` puede diferir del default del channel
Razón: el bot que atiende puede cambiar según el estado del Person. Una ChannelAccount tiene un `bot_configuration_id` default (ej. el bot preventa), pero cuando matcheamos un Person que ya es customer, switcheamos a bot postventa para esa conversation específica. La columna del channel es el default; la del conversation es el efectivo.

### Sin `archived` como estado de Conversation
Solo `open / closed`. Si después se necesita distinguir "cerrada hace 1h" vs "archivada hace 6 meses", se agrega `archived_at` como columna nullable. Por ahora `closed` + `closed_at` basta.

## Flujo de un mensaje inbound (end-to-end)

1. **Provider POST** a `/api/v1/webhooks/whatsapp/{channel_account_id}`.
2. **Router top-level** (`app/routers/webhooks.py`) carga `ChannelAccount`, valida `X-Hub-Signature-256` contra credential del Secret Manager. Si falla → `401`.
3. **Delega** a `conversations.services.webhook_processor.whatsapp.process_inbound(payload, channel_account, db)`.
4. **Processor** parsea cada `messages[]` del payload. Por cada mensaje:
   - Llama `crm.services.person.find_by_identifier_or_create(channel_type='whatsapp', identifier=msg['from'], profile=msg.get('profile'))`. Devuelve `Person`. Si es nuevo Person, este service ya crea `LeadStatus(NUEVO)` + `LeadAssignment(round_robin)` + `LeadActivity(CAMPAIGN_ATTRIBUTION)` (con `channel_account.default_campaign_id` si existe).
   - Llama `conversations.services.conversation.find_or_create_open(person_id, channel_account_id, default_bot=channel_account.bot_configuration_id)`. Si no hay `open` → crea una nueva.
   - Si la conversation es nueva y `channel_account.bot_configuration_id` está set, decide bot preventa vs postventa según `bots.services.choose_bot_for(person_id, channel_account_id)` (consulta `PersonCustomerStatus`). El bot elegido queda en `conversation.bot_configuration_id`.
   - Llama `conversations.services.message.persist_inbound(...)` que inserta `Message` (+ `MessageAttachment` si aplica). UNIQUE `(conversation_id, external_id)` previene duplicados.
   - Si `conversation.assignee_type = bot`, dispara evento al motor del bot (in-process o externo según [ADR-005, módulo bots]). El bot decide y envía respuesta vía endpoint `POST /conversations/{id}/messages`.
   - Si `conversation.assignee_type = advisor`, **no se dispara bot**. El mensaje queda en bandeja del asesor; `unread_count` incrementa.
5. **Provider POST de status** (`delivered`, `read`): processor busca `Message` por `external_id` y actualiza `delivered_at`/`read_at`/`external_status`.

## Flujo de mensaje outbound (asesor envía)

1. `POST /api/v1/conversations/{id}/messages` con `{content_type, content?, attachments?}`.
2. Service valida que `CurrentAuth.user.id == conversation.assignee_user_id` (solo el asesor que tomó puede enviar; admin también puede vía permission separada futura si se necesita).
3. **Persiste primero el `Message`** con `status=null` y `direction=outbound`. Luego intenta enviar vía SDK del proveedor (WhatsApp Cloud API).
4. Si éxito: actualiza `external_id`, `external_status='sent'`, `sent_at`.
5. Si falla: `failed_at`, `failure_reason`. Endpoint puede devolver `502` o `200` con el message marcado fallido (TBD al implementar).
6. Emite `LeadActivity(MESSAGE_SENT)` en `crm`.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `admin` | `Conversation.assignee_user_id`, `Message.sender_user_id`, `ConversationAssignmentLog` (FKs). Audit users. |
| `crm` | Matching de Person vía `PersonContactIdentifier`. `conversations` llama `crm.services.person.find_by_identifier_or_create()`. |
| `bots` | `ChannelAccount.bot_configuration_id` y `Conversation.bot_configuration_id` (FKs). Conversations decide qué bot atiende; bots procesa y responde. |
| `marketing` | `ChannelAccount.default_campaign_id` (FK opcional) para atribución del lead. |

## Diagramas

- ER: [`docs/diagrams/er-conversations.puml`](../diagrams/er-conversations.puml)
- Class: [`docs/diagrams/class-backend-conversations.puml`](../diagrams/class-backend-conversations.puml)

## Próximos pasos / TODOs deliberados

- [ ] Definir **estrategia de almacenamiento de attachments** al MVP de WhatsApp: probable GCS bucket en proyecto `proyecto-ifc-497317`, URL firmada con TTL. Documentar en ADR aparte si crece complejidad.
- [ ] Implementar la validación de **firma de webhook** por proveedor (Meta usa HMAC SHA256 con app_secret). Test smoke con payload real al desplegar.
- [ ] Considerar **rate limiting** específico para webhooks (slowapi por `channel_account_id`) — Meta puede mandar bursts altos.
- [ ] **WebSocket / SSE para inbox en vivo**: cuando el frontend de inbox necesite actualizaciones en vivo (mensaje nuevo aparece sin refresh), agregar SSE endpoint `/me/inbox/stream`. Postergado al MVP UI.
- [ ] **Búsqueda full-text** sobre `Message.content`: si la operación lo pide, agregar índice `tsvector` (Postgres) y endpoint de búsqueda.
- [ ] **Templated messages** (WhatsApp tiene plantillas pre-aprobadas para mensajes fuera de ventana de 24h): cuando aplique, modelar como `MessageTemplate` + `Message.template_name` para outbound — postergado al primer caso de uso.
