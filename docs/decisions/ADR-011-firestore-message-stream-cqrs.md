# ADR-011: Stream de mensajes en Firestore (CQRS read-model) — control plane Postgres + data plane Firestore + Transactional Outbox + Custom-Token auth

> **Status**: Accepted
> **Date**: 2026-06-03
> **Deciders**: @daniel, @marco
> **Relacionado**: revisa [ADR-004](ADR-004-conversation-channel-account.md) (`Conversation` + `ChannelAccount`; el `Message` deja de ser entidad Postgres relacional); usa [ADR-010](ADR-010-runtime-secret-resolution.md) para las credenciales de WhatsApp (el Firebase Admin, en cambio, usa ADC, no Secret Manager).

## Context

El módulo `conversations` (#5) es un **inbox de mensajería** operado por asesores: el hilo de chat (right pane) debe actualizarse **en tiempo real** cuando entra un mensaje del contacto, cuando el asesor envía, y cuando llegan los callbacks de estado de WhatsApp (`delivered`/`read`/`failed`). La spec previa del módulo modelaba `Message` y `MessageAttachment` como **tablas Postgres relacionales** y leía el hilo por **polling**. Eso funciona, pero el polling tiene un techo de UX (latencia perceptible, refrescos innecesarios) y un costo creciente a medida que el inbox se llena de asesores con hilos abiertos.

La pregunta a decidir **ahora** es **dónde y cómo se persisten los mensajes** para habilitar el real-time del hilo **sin** romper los tres principios estructurales del template:

1. **El browser no muta el backend**: toda escritura (enviar, tomar, liberar, cerrar) pasa por el servidor (Next server action → backend → Meta + store), nunca el cliente directo al store.
2. **JWT server-side / RBAC como fuente de verdad**: quién ve qué lo decide el access token y los permisos del backend, no un store con su propia auth paralela.
3. **Postgres como fuente de verdad** del estado relacional/operativo (el `crm` enlaza `lead_activity.related_conversation_id → conversation`; el inbox se filtra/ordena con SQL; el UNIQUE parcial "una conversación abierta por par" es una invariante relacional).

La elección no es trivial porque un dual-store ingenuo (escribir a Postgres **y** a un store real-time en dos pasos) introduce el problema del **dual-write**: si una de las dos escrituras falla, los stores divergen y se pueden **perder mensajes** — inaceptable en mensajería.

> **Nota de industria.** El stream de chat a escala suele resolverse con un **wide-column store** (Cassandra/Scylla/Bigtable): tablas anchas, partición por `conversation_id`, clustering por tiempo — óptimo para append + range-scan del hilo. Pero ese camino **no trae sincronización real-time al cliente**: habría que montar aparte un fan-out (websockets/SSE) y su backplane. **Firestore (Native mode)** ofrece exactamente lo que falta: **listeners real-time del Web SDK** (`onSnapshot`) + **Security Rules** que se evalúan por documento, todo gestionado, sin operar infra de streaming. Para el volumen de un inbox de clínica el modelo de costos de Firestore (reads por documento) es holgado, y el real-time client sync es justo el diferenciador que justifica traer un segundo store. **El usuario confirmó esta decisión el 2026-06-03**, revirtiendo la nota previa del README ("Persistencia de mensajes: Postgres, no Firestore").

## Decision

**Persistir el stream de mensajes en Cloud Firestore (Native mode) como un read-model en tiempo real (CQRS), manteniendo Postgres como fuente de verdad del control plane, sincronizados por un Transactional Outbox, y exponiendo la lectura real-time al browser vía Custom Tokens minteados por el backend + Security Rules que espejan el RBAC.**

### 1. Split de datos — control plane Postgres / data plane Firestore

- **Postgres = control plane / fuente de verdad** del estado relacional y operativo:
  - `channel_account`, `conversation` (con sus denormalizados `last_message_at`/`last_message_preview`/`unread_count` y el UNIQUE parcial "una abierta por par") y `conversation_assignment_log` — **se quedan en Postgres**. `Conversation` **no** se va a Firestore: preserva la FK `lead_activity.related_conversation_id → conversation`, las invariantes y los filtros del inbox (SQL).
  - **`message_outbox` (NUEVO, Postgres)** — cola transaccional durable Postgres→Firestore (ver §2).
  - **`message` / `message_attachment` dejan de ser tablas Postgres**: su contenido vive en Firestore. Los **enums y los schemas Pydantic** del mensaje se conservan como **contrato de API** + **shape del doc** Firestore.
- **Firestore (Native mode) = data plane / read-model real-time** del stream de mensajes (proyección):
  - `conversations/{cid}` — espejo liviano del `Conversation` de Postgres (para Security Rules + inbox live): `status`, `assignee_user_id`, `allowed_reader_ids: [uid...]`, `channel_account_id`, `person_name`, `person_id`, `last_message_at`, `last_message_preview`, `unread_count`, `updated_at`. `cid` = el UUID del `Conversation` de Postgres (clave de join). Escrito **solo** por el backend (Admin SDK).
  - `conversations/{cid}/messages/{mid}` — el mensaje (`direction`, `sender_type`, `content_type`, `content`, `external_id`, `external_status`, timestamps, `attachments`, `provider_payload`, …). `mid` = `wamid` (inbound) / uuid (outbound) → idempotencia natural por doc-id.
  - **Native mode (Standard edition)** — requerido para los listeners real-time del Web SDK + Security Rules (no Datastore mode, no Enterprise/MongoDB-compat). Location `us-central1` (colocado con Cloud SQL/Run; permanente). **Una database Firestore por entorno** (named DBs `medisage-qa` / `medisage`, espejando el patrón de Cloud SQL); el backend elige por `ENV_NAME`.

### 2. Consistencia — Transactional Outbox + idempotencia (resuelve el dual-write)

- **Inbound (webhook síncrono):** verifica firma → **TX Postgres atómica** que hace `find_by_identifier_or_create` + `find_or_create_open` + `INSERT message_outbox(id=mid, op=message_create) ON CONFLICT (id) DO NOTHING` (dedup real) + (solo si insertó algo nuevo) `unread_count++`/denorm + `INSERT message_outbox(op=conversation_upsert)` + `lead_activity.log` → COMMIT → return 200. Un **relay** (MVP: `BackgroundTasks`; producción: Cloud Tasks) drena el outbox y escribe los docs a Firestore con el Admin SDK (`set(doc_id=mid)` = create-if-absent idempotente), con reintentos/backoff. Si la TX falla, **nada** se aplica; si el relay aún no corrió, el mensaje **no se pierde** (vive durable en el outbox).
- **Status callbacks (`delivered`/`read`/`failed`):** el backend actualiza **directo el doc Firestore** vía Admin SDK (best-effort, no toca Postgres; opcionalmente por outbox `op=message_status` si se quisiera durabilidad).
- **Outbound (asesor envía):** TX Postgres `INSERT message_outbox(id=uuid, op=message_create, status=pending)` + denorm + `conversation_upsert` → COMMIT → relay/inline escribe el doc (status=pending, el asesor lo ve instantáneo) → llama Meta Graph API → update doc Firestore con `{external_id, external_status}` (sent o failed). Reintento = mensaje nuevo (mid uuid nuevo).
- **Postgres manda; Firestore es proyección eventual** (latencia ms–seg). La **idempotencia** ya no es el UNIQUE parcial de la tabla `message`, sino el **`message_outbox.id` UNIQUE = mid** (`ON CONFLICT DO NOTHING`) + el **doc-id = mid** en Firestore (`set` create-if-absent): doble dedup. Audit/analítica de mensajes: export Firestore→BigQuery (nativo GCP), no Postgres.

### 3. Seguridad — Custom Tokens + Security Rules (no rompe "browser no muta backend / JWT server-side / RBAC")

- El **backend** carga el **Firebase Admin SDK** (`firebase-admin`), init vía **ADC** (la SA de Cloud Run `medisage-sa[-qa]`, sin key file en prod), con roles `roles/datastore.user` (Firestore RW) + `roles/iam.serviceAccountTokenCreator` sobre sí misma (firmar custom tokens vía signBlob). El proyecto Firebase se linkea al GCP project `proyecto-ifc-497317`.
- Endpoint **`POST /conversations/realtime/token`** (gated `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ`) → `create_custom_token(uid=user.id, developer_claims={scope:"conversations", is_advisor, can_read_all})`. **El JWT/RBAC es la fuente de verdad** (gatea quién recibe token y con qué claims; `can_read_all=true` solo para `CONVERSATIONS_READ` = bandeja global/supervisor).
- El browser hace `signInWithCustomToken(...)` → ID token (1h, auto-refresh mientras viva la sesión medisage) → abre **listeners READ-ONLY**. Logout / cambio de permisos: `revoke_refresh_tokens(uid)`.
- **`firestore.rules`** (versionado en el repo, desplegado por CI): `read` permitido si `scope == 'conversations'` y (`can_read_all == true` **o** `request.auth.uid in resource.data.allowed_reader_ids`); `write: if false` siempre (clientes nunca escriben; solo el Admin SDK, que bypassa las rules). `allowed_reader_ids = [assignee_user_id] + [admins/supervisores]`, mantenido por el backend vía el outbox (`conversation_upsert`) cuando cambia la asignación. **El browser solo LEE** el stream que está autorizado a ver; **toda** mutación va browser → Next server → backend → Meta + Firestore (Admin SDK).

## Alternatives Considered

### Opción A — Todo Postgres + polling del hilo (statu quo de la spec previa)
- **Pros**: un único store, cero infra nueva, cero segundo SDK, idempotencia por UNIQUE parcial, ya probado en los módulos previos.
- **Cons**: **sin real-time nativo** — el hilo se refresca por polling (latencia perceptible, refrescos vacíos, costo creciente por asesor/hilo). La UX del inbox queda por debajo de lo esperable en mensajería.
- **Rechazada porque**: el requisito central del rediseño es el real-time del hilo, que Postgres + polling no da de forma nativa.

### Opción B — Todo Postgres + SSE (Server-Sent Events) para el push del hilo
- **Pros**: mantiene un único store (Postgres), no agrega Firestore ni un segundo SDK, el push viaja por el mismo backend con su JWT/RBAC.
- **Cons**: hay que **operar el fan-out** (conexiones SSE de larga vida, backplane para multi-instancia, reconexión/replay, throttling de CPU en Cloud Run para conexiones colgadas); es trabajo de plataforma recurrente que Firestore entrega gestionado.
- **Rechazada porque**: aunque es **viable**, el usuario eligió Firestore (2026-06-03) por su **real-time client sync + Security Rules gestionados**, que evitan construir y mantener el backplane de streaming.

### Opción C — Todo a Firestore, incluido `Conversation`
- **Pros**: un solo store para conversación y mensajes; menos sincronización.
- **Cons**: rompe la **FK `lead_activity.related_conversation_id → conversation`** de crm (Firestore no tiene FKs ni joins relacionales), y obliga a reimplementar los **filtros/orden del inbox** y el **UNIQUE parcial 1-open** fuera de SQL (más frágil y caro en Firestore).
- **Rechazada porque**: el control plane es genuinamente relacional; sacarlo de Postgres pierde integridad referencial con crm y las queries del inbox sin ganar nada.

### Opción D — Dual-write sin outbox (backend escribe Postgres y Firestore en dos pasos)
- **Pros**: simple de codear a primera vista (un `INSERT` + un `set`).
- **Cons**: **dual-write sin garantía** — si la segunda escritura falla (o el proceso muere entre ambas), los stores divergen y se **pierden o duplican** mensajes. No hay transacción distribuida entre Postgres y Firestore.
- **Rechazada porque**: la consistencia de mensajería no es negociable; el **Transactional Outbox** (escribir el intent dentro de la misma TX Postgres y drenarlo con un relay idempotente) es justamente el patrón que elimina esta clase de bug.

### Opción E (Aceptada) — CQRS: control plane Postgres + data plane Firestore + Transactional Outbox + Custom-Token auth
- Ver Decision (§1 split, §2 outbox, §3 auth). Real-time gestionado, sin pérdida de mensajes, sin romper los principios del template.

## Consequences

### Positivas
- **Real-time del hilo gestionado**: el right pane se actualiza vía `onSnapshot` (inbound, outbound optimista server-driven, callbacks de estado) sin operar infra de streaming.
- **Sin pérdida de mensajes**: el Transactional Outbox (intent dentro de la TX Postgres + relay idempotente con `set(doc_id=mid)`) elimina el dual-write; el outbox es durable y reintenta.
- **Doble idempotencia**: `message_outbox.id` UNIQUE (`ON CONFLICT DO NOTHING`) + doc-id `mid` en Firestore (`set` create-if-absent) → webhooks repetidos no duplican ni inflan `unread_count`.
- **Principios del template intactos**: el browser **solo lee** (Security Rules `write: if false`), el **RBAC del backend** decide quién recibe token y con qué claims, y **Postgres sigue siendo la fuente de verdad** del estado operativo (crm/inbox/invariantes intactos).
- **Aislamiento CQRS**: el data plane (Firestore) es una **proyección** descartable/reconstruible desde Postgres + outbox; el control plane no depende de Firestore para su integridad.

### Negativas / Trade-offs
- **Más piezas móviles**: Firestore (Native mode, named DBs por entorno) + Firebase Admin SDK (backend) + tabla `message_outbox` + relay (BackgroundTasks → Cloud Tasks) + `firestore.rules` versionadas + el **segundo SDK** en el frontend (Web SDK `firebase/app`+`auth`+`firestore`). Más superficie de mantenimiento y deploy.
- **Costo de reads de Firestore**: el modelo cobra por documento leído; un inbox muy activo con muchos listeners suma reads. Holgado para el volumen de una clínica, pero hay que vigilarlo (y considerar paginar/limitar el hilo).
- **Consistencia eventual del read-model**: Firestore va por detrás de Postgres por ms–seg (latencia del relay); el control plane es consistente al instante, la proyección no. Aceptable para un inbox.
- **Dos planos de auth a mantener en sincronía**: `allowed_reader_ids` en los docs debe reflejar la asignación de Postgres; lo mantiene el backend vía `conversation_upsert` en el outbox al cambiar la asignación, y `revoke_refresh_tokens` al cambiar permisos.
- **Mitigación**: el **aislamiento CQRS** acota el blast radius — Firestore es proyección, no fuente de verdad; ante drift, se re-proyecta desde Postgres + outbox.

### Lo que esto nos obliga a hacer
- **F1**: agregar `firebase-admin` a `pyproject.toml`; crear `app/core/firestore.py` (Admin SDK init por ADC, lazy import; `get_db()`, `mint_custom_token`, `write_message_doc`, `upsert_conversation_doc`, `update_message_status`); **provisionar Firestore** (DB Native mode `medisage-qa`/`medisage`, location `us-central1`) y desplegar `firestore.rules` base; conceder a la SA `roles/datastore.user` + `roles/iam.serviceAccountTokenCreator`; linkear el proyecto Firebase a `proyecto-ifc-497317`. El endpoint `realtime/token` puede ir en F1 o F2.
- **F2**: crear `message_outbox` (migración `0016_conv_threads`, **sin** tablas `message`/`message_attachment`); `services/message.persist_inbound` (outbox + denorm en la TX) + `relay_outbox` (relay a Firestore); escribir los docs `conversations/{cid}` + `.../messages/{mid}` (Admin SDK); `firestore.rules` con la lógica de `allowed_reader_ids`; frontend `lib/firebase/client.ts` + `getRealtimeToken()` action + thread con `onSnapshot` read-only (el listado sigue por polling Postgres).
- **F3**: `conversation_upsert` al outbox en take/release/close/reopen (refleja `assignee_user_id`/`allowed_reader_ids`); outbound real (Meta + Firestore via Admin SDK + estados en vivo).
- **Smoke/local sin GCP**: lazy import de `firebase_admin` (no al import del módulo) + fallback/mocks/emulador en los tests — el smoke (sqlite, single-thread) **nunca** debe golpear Firestore real (igual que el resolver de secretos de ADR-010).
- **Mantener `firestore.rules` versionadas** en el repo y desplegadas por CI por entorno.

## Referencias

- [ADR-004](ADR-004-conversation-channel-account.md) — `Conversation` + `ChannelAccount` (revisado 2026-06-03: `Message` deja de ser entidad Postgres relacional y pasa a Firestore como read-model; la idempotencia ahora es outbox-unique + doc-id, no el UNIQUE parcial de `message`).
- [ADR-010](ADR-010-runtime-secret-resolution.md) — resolución de secretos por-cuenta (WhatsApp) vía Secret Manager SDK; **distinto** del Firebase Admin, que init por **ADC** (no Secret Manager).
- [ADR-009](ADR-009-forward-fk-deferred-cross-module.md) — la FK aditiva `lead_activity.related_conversation_id → conversation` sigue válida porque `Conversation` **se queda** en Postgres.
- Fichas del módulo: [`conversations/README.md`](../modules/conversations/README.md), [`conversations/backend.md`](../modules/conversations/backend.md) (`app/core/firestore.py`, `message_outbox`, relay), [`conversations/frontend.md`](../modules/conversations/frontend.md) (`lib/firebase/client.ts`, `onSnapshot`).
- Código futuro: `backend/app/core/firestore.py`, `backend/app/modules/conversations/{models/message_outbox.py,services/message.py,routers/realtime.py}`, `firestore.rules`.
- Docs externos: Firestore Native mode <https://cloud.google.com/firestore/docs/firestore-or-datastore> · Security Rules <https://firebase.google.com/docs/firestore/security/get-started> · Custom Tokens <https://firebase.google.com/docs/auth/admin/create-custom-tokens> · Transactional Outbox <https://microservices.io/patterns/data/transactional-outbox.html> · export a BigQuery <https://cloud.google.com/firestore/docs/export-import-bigquery>.
