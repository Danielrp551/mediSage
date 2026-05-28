# ADR-004: Conversation + ChannelAccount como par central de la mensajería multicanal

> **Status**: Accepted
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

## Referencias

- Ficha del módulo: [`docs/modules/conversations.md`](../modules/conversations.md)
- ADR relacionado: [ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) — `Conversation.person_id` apunta a `Person`, no a lead/customer; coherente con el modelo de identidad única acordado en CRM.
- Patrón en código futuro: `backend/app/modules/conversations/`, `backend/app/routers/webhooks.py`.
- Sobre Meta WhatsApp Cloud API webhook signature: el handler valida `X-Hub-Signature-256` con HMAC SHA256 sobre el body raw, usando `app_secret` resuelto desde el secret apuntado por `channel_account.secret_name`. Documentación: <https://developers.facebook.com/docs/graph-api/webhooks/getting-started#validating-payloads>.
