# ADR-004: Conversation + ChannelAccount como par central de la mensajería multicanal

> **Status**: Accepted (act. 2026-06-02)
> **Date**: 2026-05-28
> **Deciders**: @daniel, @marco

## Context

Medisage MVP opera **WhatsApp** como único canal de mensajería, pero el diseño debe quedar listo para sumar **Telegram, Web chat, Instagram DM y otros canales** sin migración estructural.

El dominio impone tres requisitos no triviales:

1. **Multi-cuenta por canal**: la clínica puede operar **varios números de WhatsApp Business** (uno por vertical, uno por sede, uno para preventa y otro para postventa). Cada uno tiene su propio access token, su propio bot por defecto, y posiblemente su propia campaña de atribución.
2. **Conversación pertenece al humano, no al hilo comercial**: el ciclo lead↔customer (módulo `crm`) sucede en paralelo al ciclo de la conversación. Una persona puede tener múltiples conversaciones cerradas en el tiempo y una activa.
3. **Mensaje viaja como ciudadano de primera clase**: con su `external_id`, status (sent/delivered/read), attachments tipados, y audit trail inmutable.

La decisión es **cómo modelar el ingress de mensajería** para soportar todo lo anterior **sin** sobre-ingenierizar para canales que aún no existen.

## Decision

**Modelar `ChannelAccount` y `Conversation` como dos entidades separadas con FK simple entre ellas**:

- **`ChannelAccount`** es la **cuenta operativa** que tiene la clínica en un proveedor: `(channel_type, external_identifier)` único. Lleva la config (`secret_name` apuntando a GCP Secret Manager, `bot_configuration_id` default, `default_campaign_id` para atribución).
- **`Conversation`** es el **hilo entre una `Person` y una `ChannelAccount`**. Múltiples conversations pueden existir por par (a lo largo del tiempo), pero **una sola con `status='open'` simultáneamente** (UNIQUE partial).
- **`Message`** apunta a una `Conversation` y tiene `direction ∈ {inbound, outbound}` + `sender_type ∈ {contact, bot, advisor, system}`. Polimórfico por contenido pero no por canal: el canal vive en la `Conversation`.
- **Webhooks** son **top-level**, fuera de cualquier módulo, en `app/routers/webhooks.py`. Validan firma del provider (no JWT) y delegan a `conversations.services.webhook_processor.<channel>.process_inbound(payload, channel_account, db)`.

El handoff bot↔asesor vive como **estado plano en `Conversation`** (`assignee_type`, `assignee_user_id`) más una **tabla de log inmutable** (`ConversationAssignmentLog`) que captura el historial.

## Alternatives Considered

### Opción A — Tabla por canal (polimorfismo estricto)

`whatsapp_conversation`, `telegram_conversation`, `web_conversation`, cada una con sus columnas específicas. `Message` polimórfico también.

- **Pros**:
  - Cada canal en su tabla con sus columnas — sin nullables sospechosos.
  - Tipos fuertes en cada modelo (e.g. WhatsApp tiene `wa_id` obligatorio, Telegram tiene `chat_id`).
- **Cons**:
  - **FKs polimórficas en módulos consumidores**: `crm.LeadActivity.related_conversation_id` tendría que ser `(conversation_type, conversation_id)` — anti-pattern en SQL relacional.
  - Cada canal nuevo requiere **migración de schema** (crear tabla + endpoints + queries específicos).
  - Reportes globales ("cuántas conversaciones activas tiene la clínica") obligan a `UNION ALL` por tabla.
  - El handoff (`assignee_type` + log) tendría que existir replicado en cada tabla de canal, o vivir en una tabla aparte con la misma FK polimórfica del problema anterior.
- **Rechazada porque**: los costos de polimorfismo SQL exceden el beneficio de "tipos fuertes por canal", que en la práctica se resuelve igual de bien con `provider_payload: jsonb` en `Message` para guardar el payload del canal.

### Opción B — Solo `Conversation` con `channel_type` enum (sin `ChannelAccount`)

- **Pros**:
  - Simple: una tabla, un enum. Menos joins.
- **Cons**:
  - **No soporta multi-cuenta por canal**. Una clínica con dos números WhatsApp Business no puede distinguirlos a nivel BD — el `channel_type='whatsapp'` no dice cuál. Esto rompe:
    - **Atribución de campaña**: una campaña "Botox 2x1" usa un número distinto al de "Brackets" para reportar conversiones. Sin `ChannelAccount`, no hay forma de saber por dónde entró el lead.
    - **Bot por canal**: queremos que el bot preventa atienda un número y el bot postventa otro. Sin `ChannelAccount`, hay que hardcodear lógica que decide bot por contenido (mucho más frágil).
    - **Credenciales**: si tenemos un solo token de WhatsApp en config global, no podemos rotar uno sin tocar el otro, ni migrar uno sin migrar todo.
  - El **webhook** tendría que identificar `channel_type` y luego buscar la conversation por el `from` — sin tabla intermedia que asocie el endpoint del webhook a una cuenta concreta.
- **Rechazada porque**: confirmado por el usuario que multi-cuenta por canal es requisito (preventa/postventa en números separados, verticales con números propios).

### Opción C — `Channel` (config global del canal) + `Conversation` apunta directo al `channel_type` enum

Una tabla `channel` con la config (token, etc.) compartida por canal, sin distinción de cuentas. `Conversation` lleva `channel_type` directo.

- **Pros**: intermedio entre A y B.
- **Cons**: hereda el problema de B (no soporta multi-cuenta). La tabla `channel` solo tendría 4-5 filas con configuración global, lo que es esencialmente lo mismo que variables de entorno.
- **Rechazada porque**: no resuelve el problema real.

### Opción D — Aceptada: `ChannelAccount` + `Conversation` con FK

- `ChannelAccount` es la **unidad operativa** y unidad de configuración.
- `Conversation` apunta al `channel_account_id`, no al `channel_type` directo.
- Webhook se monta como `/api/v1/webhooks/{channel_type}/{channel_account_id}` — la URL identifica la cuenta exacta.
- `Message`, `MessageAttachment`, `ConversationAssignmentLog` viven todos colgados del `Conversation` — sin polimorfismo por canal.

## Consequences

### Positivas

- **Multi-cuenta nativa**: agregar un segundo número WhatsApp es un INSERT en `ChannelAccount`, no una migración de schema.
- **FKs simples en módulos consumidores**: `crm.LeadActivity.related_conversation_id` apunta a `conversation.id`, sin polimorfismo.
- **Webhook URL es identifying**: la URL `/api/v1/webhooks/whatsapp/{channel_account_id}` ya dice qué cuenta procesa — no hay que parsear payload para identificar destino.
- **Bot/campaña por cuenta**: `ChannelAccount.bot_configuration_id` y `default_campaign_id` permiten configurar comportamiento por número sin código adicional.
- **Atribución del lead funciona out of the box**: cuando `find_by_identifier_or_create` crea un Person nuevo, lee `channel_account.default_campaign_id` y lo guarda en `PersonLeadStatus.source_campaign_id`.
- **Agregar canal nuevo** = agregar processor en `webhook_processor/<canal>.py` + endpoints en `app/routers/webhooks.py`. Cero migración de tablas.

### Negativas / Trade-offs

- **Más joins en queries cotidianos**: listar el inbox carga `Conversation → Person → ChannelAccount → User`. Mitigado con `selectinload` y columnas denormalizadas en `Conversation` (`last_message_preview`, `unread_count`, `last_message_at`).
- **Validación de UNIQUE partial sobre `Conversation`**: la regla "una sola open por (person, channel_account)" depende de un `CREATE UNIQUE INDEX ... WHERE`. Postgres lo soporta; en aiosqlite (tests) puede que la regla deba validarse en service además.
- **`ChannelAccount.secret_name` introduce dependencia con Secret Manager** en runtime — el código no corre sin GCP en entorno cloud. Para local dev, el código de `get_credentials()` cae a env vars (`WHATSAPP_TOKEN_{channel_account_id}` o similar) si `secret_name` viene `NULL` o si `USE_LOCAL_SECRETS=true`. Documentar en `services/channel_account.py`.

### Lo que esto nos obliga a hacer

- **Webhooks top-level** en `app/routers/webhooks.py` registrados en `app/main.py`. Sin JWT, validan firma del provider.
- **`services/webhook_processor/`** con un módulo por canal. Empieza con `whatsapp.py`; `telegram.py` y otros se agregan cuando aplique.
- **`services/channel_account.get_credentials(ca)`** que resuelve `secret_name` contra GCP Secret Manager (cliente ya configurado en el template para `SECRET_KEY`). Cache por TTL razonable (10 min) para no golpear Secret Manager por cada webhook.
- **Migration que cree los UNIQUE partial indexes** sobre `Conversation` (`status='open'`) y `Message` (`external_id IS NOT NULL`). Postgres específico — documentar que el motor objetivo es Postgres 16 (template y prod ya lo asumen).
- **Tests** deben cubrir:
  - Doble webhook con el mismo `external_id` no duplica `Message`.
  - Crear segunda conversation `open` para mismo `(person, channel_account)` falla.
  - Tomar/release/close transiciona `assignee_type` y cierra/abre `ConversationAssignmentLog`.
  - `find_or_create_open` reusa la abierta o crea una nueva si no hay.

## Actualización (2026-06-02)

Las decisiones se confirmaron con el usuario en la fase de documentación del módulo (ver la spec autoritativa y el [README consolidado](../modules/conversations/README.md)). El ADR sigue **Accepted**: la decisión central (`ChannelAccount` + `Conversation` con FK simple, webhooks top-level, handoff como estado plano + log inmutable) se mantiene. Los puntos siguientes **corrigen** o **refinan** el texto original.

### Corrección sobre Secret Manager

El texto de "Lo que esto nos obliga a hacer" afirmaba que `get_credentials()` resolvería `secret_name` contra GCP Secret Manager usando un **"cliente ya configurado en el template para `SECRET_KEY`"**. Eso es **falso**: el template hoy inyecta secretos fijos por env a **deploy-time** vía `--set-secrets` de Cloud Run (`SECRET_KEY`/DB-creds llegan como **env vars** que la app lee por `Settings`, **sin SDK**). No existe cliente de Secret Manager en el código.

Las credenciales **por-`ChannelAccount`** necesitan resolución **dinámica** (multi-cuenta sin redeploy), así que se introduce el SDK `google-cloud-secret-manager` con un resolver en runtime (`app/core/secrets.py`, cache TTL + fallback env en local/test). Esa decisión vive en su propio ADR → ver **[ADR-010](ADR-010-runtime-secret-resolution.md)**. El fallback a env de `get_credentials()` que describe la sección "Negativas / Trade-offs" sigue válido.

### Convención de updates: PUT, no PATCH

El codebase usa **`PUT`** (no `PATCH`) para los updates de `ChannelAccount` (`PUT /channel-accounts/{id}`), consistente con el resto de los módulos (catalog/clinic/staff/crm). Cualquier referencia a PATCH queda corregida a PUT.

### Asignación de la conversación nueva = auto al dueño del lead, con fallback

El diseño original dejaba implícito que la conversación entra `unassigned` siempre. **Reemplazado**: al crear una conversación nueva para una `Person`, se **auto-asigna** al asesor de su `LeadAssignment` activo (el round-robin que ya hace crm, leído vía `lead_assignment_repository.advisor_map`); si la Person no tiene asesor → `unassigned` (bandeja compartida). La auto-asignación abre un `ConversationAssignmentLog` con `by_actor_user_id = NULL` (automático). El asesor puede tomar/reasignar igual. Continuidad "mis leads = mis chats".

### Adjuntos texto-primero

`MessageAttachment` se **modela** desde el inicio (tabla + enum `AttachmentType`, creada en la migración de threads para no re-migrar), pero el processor del MVP procesa **solo texto**. El download/storage de media (lazy proxy vs GCS, a re-confirmar) se **difiere a F4**.

### Webhook entrante síncrono en el MVP

El procesamiento inbound es **síncrono** antes del 200 (verify firma + dedup + resolver Person + persistir): es rápido y no hay bot que genere auto-reply lento, así que **no** se usa `BackgroundTasks`. Cuando `bots` (#6) agregue auto-reply lento → mover a cola / `--no-cpu-throttling --min-instances 1`. (Difiere del patrón general "200 inmediato + BackgroundTasks" justamente porque no hay trabajo lento aún.)

### Emisión a la timeline de crm: solo handoff, no por-mensaje

conversations emite a `crm.LeadActivity` **solo** `CONVERSATION_TAKEN` (al tomar) y `CONVERSATION_RELEASED` (al liberar). **NO** emite `MESSAGE_SENT` por-mensaje (evita inundar el timeline lead-céntrico y la escritura cross-módulo en el hot path del envío). `MESSAGE_SENT` queda reservado en el enum para un uso futuro (ej. "primer contacto"). Estos eventos no están en `ADVISOR_ACTIVITY_TYPES`, así que el composer del asesor de crm no puede editarlos/borrarlos → audit trail inmutable.

### Hardening de `find_by_identifier_or_create` con advisory lock

`crm.find_by_identifier_or_create` (que invoca el webhook processor) hacía get-then-insert **sin lock** (no tenía callers); bajo webhooks concurrentes para el MISMO número nuevo, dos requests insertarían → `IntegrityError`. Se agrega un **advisory lock transaccional Postgres** (`pg_advisory_xact_lock`) al inicio de la función, keyed por `(channel_type, identifier)` (no-op en sqlite). La hardening vive dentro de crm (la función dueña del dedup) y beneficia a cualquier caller.

### FK aditiva `lead_activity.related_conversation_id → conversation`

conversations **es el dueño** de la relación (ADR-009): la columna `lead_activity.related_conversation_id` ya existe en crm (`varchar(36)` + index, **sin** constraint). conversations agrega la **FK constraint aditiva** (`fk_lead_activity_conversation`, Postgres-only) en la **migración 0016** (threads). Seguro (todos los valores actuales son NULL); **sin** `relationship` ORM (mantiene el modelo crm intacto).

### Mensajes de sistema en el hilo: no se insertan en el MVP

El handoff (tomar/liberar/cerrar/reabrir) **NO** inserta un `Message(sender_type=system, content_type=system_notification)` en el hilo en el MVP. Se ve vía el `assignment_history` (`ConversationAssignmentLog`) en el header del hilo + el badge "Asignado a X". Los valores de enum `SenderType.system` / `ContentType.system_notification` quedan **reservados** (forward, no se emiten en el MVP).

## Referencias

- Ficha del módulo: [`docs/modules/conversations/README.md`](../modules/conversations/README.md) (overview consolidado; ver también `backend.md`/`ui.md`/`frontend.md`)
- ADR relacionado: [ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) — `Conversation.person_id` apunta a `Person`, no a lead/customer; coherente con el modelo de identidad única acordado en CRM.
- Patrón en código futuro: `backend/app/modules/conversations/`, `backend/app/routers/webhooks.py`.
- Sobre Meta WhatsApp Cloud API webhook signature: el handler valida `X-Hub-Signature-256` con HMAC SHA256 sobre el body raw, usando `app_secret` resuelto desde el secret apuntado por `channel_account.secret_name`. Documentación: <https://developers.facebook.com/docs/graph-api/webhooks/getting-started#validating-payloads>.
