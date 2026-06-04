# ADR-012: Despacho del turno del bot vía Cloud Tasks (no síncrono, no BackgroundTasks)

> **Status**: Accepted
> **Date**: 2026-06-04
> **Deciders**: @daniel, @marco

## Context

El módulo `bots` (#6) atiende automáticamente las conversaciones cuando `Conversation.assignee_type='bot'`: cada mensaje inbound dispara un **turno** del bot. Un turno es trabajo **lento y must-complete**:

- Una llamada al LLM (gpt-4.1-mini / Claude) tarda **segundos**, y un turno puede encadenar **2–4 round-trips** si el modelo invoca tools (tool-calling loop) → **5–20 s** end-to-end.
- El turno **debe completar** (responderle al cliente) y **debe reintentarse** ante fallos transitorios del LLM / la red / un tool.

El turno se origina en el webhook de WhatsApp (`conversations.process_inbound`), que tiene tres restricciones duras (ya conocidas del módulo `conversations`, ver [ADR-011](ADR-011-firestore-message-stream-cqrs.md) y el relay síncrono de F2):

1. **Meta exige el 200 en segundos.** Si el webhook tarda, Meta reintenta y eventualmente deshabilita la suscripción. El webhook **no puede bloquear** esperando el LLM.
2. **Cloud Run cpu-throttling.** Por default, al enviar la respuesta la CPU baja a ~0 → cualquier trabajo in-process post-respuesta se cuelga (esto es exactamente lo que rompió el relay vía `BackgroundTasks` en `conversations` F2: la sesión nueva del task no veía los commits + throttling; ver el análisis en [[feedback-medisage-operational-lessons]] §9).
3. **`min-instances=0`** → la instancia puede ser reapeada tras responder, matando cualquier trabajo en background.

El relay de `conversations` quedó **síncrono** porque era rápido (writes Firestore de ms). El turno del bot **NO puede** serlo: es lento y bloquearía el webhook. Hay que sacarlo del request del webhook a un mecanismo asíncrono **durable**.

## Decision

**El turno del bot se despacha vía Google Cloud Tasks.**

- El webhook de `conversations`, tras su pipe síncrono (persist_inbound + relay a Firestore), si `conv.assignee_type=='bot'`, **encola una Cloud Task** (operación rápida) con `{conversation_id, input_message_id}` en la cola `medisage-bot-turns[-qa]` → devuelve **200 a Meta** de inmediato.
- Cloud Tasks entrega la task como un **POST HTTP fresco** a un endpoint interno `POST /api/v1/bots/engine/dispatch`. Ese request **tiene CPU asignada** (es un request real, sin throttling) → ahí corre `bots.engine.dispatch_turn` (LLM + tools + `send_bot_outbound` + traza `BotEvent`/`BotToolCall`).
- El endpoint `/engine/dispatch` **NO usa el RBAC del template** (no hay usuario): se autentica con el **token OIDC** que Cloud Tasks firma con la SA invoker (audience = la URL del endpoint), o con un **shared-secret header** (`BOT_DISPATCH_SECRET`) como variante MVP. NO es alcanzable por el browser.
- `app/core/cloud_tasks.py` encapsula el cliente (lazy, molde de `secrets.py`/`firestore.py`) + `enqueue_turn(...)`.

Cloud Tasks aporta de fábrica: **at-least-once delivery**, **reintentos con backoff exponencial**, **max-attempts → dead-letter**, **rate/concurrency por cola** (protege los rate-limits del LLM + el pool de DB), scheduling/delay, y **dedup por task-name** (idempotencia). El endpoint de dispatch debe ser idempotente por turno (el `ConversationBotState.turn_count` + el `BotEvent` UNIQUE `(conversation_id, turn_number)` ayudan).

## Alternatives Considered

### A — FastAPI `BackgroundTasks` (+ `--no-cpu-throttling` + `min-instances≥1`)
La preferencia previa del equipo ([[feedback-webhook-async]]) era minimizar piezas con `BackgroundTasks`.
- **Pros**: cero infra extra; una sola pieza.
- **Cons**: **F2 ya demostró que no funciona confiable en Cloud Run** para trabajo must-complete (sesión nueva no ve los commits del request + throttling). Aun forzando `--no-cpu-throttling` + `min-instances≥1`: **sin durabilidad** (se pierde en crash/deploy), **sin reintentos/backoff/dead-letter**, **sin control de concurrencia** (un pico de inbound = N turnos LLM concurrentes saturando rate-limits + pool DB), y compite por CPU con los requests vivos.
- **Rechazada porque**: el turno del bot es el caso de trabajo lento+durable+con-reintentos para el que `BackgroundTasks` es justamente inadecuado en serverless. Lo que F2 toleró para el relay rápido (al hacerlo síncrono) no aplica acá.

### B — Pub/Sub push
Topic + subscription push que POSTea a un endpoint.
- **Pros**: durable, reintentos, dead-letter.
- **Cons**: su semántica natural es **fan-out/broadcast** (múltiples suscriptores a un evento). Para "un turno por mensaje, con concurrencia controlada por cola, scheduling/delay y dedup por task" es menos preciso: Cloud Tasks modela exactamente una **cola de tareas dirigidas** con control fino de rate y reintentos por-task.
- **Rechazada (preferencia)**: viable, pero Cloud Tasks es la herramienta más precisa para este patrón 1→1. (Si a futuro hay fan-out de eventos del bot, Pub/Sub se suma sin romper esto.)

### C — Síncrono en el webhook (como el relay de F2)
Correr el LLM dentro del request del webhook.
- **Rechazada porque**: viola la restricción #1 (Meta timeout) — el LLM tarda segundos; el webhook se colgaría y Meta deshabilitaría la suscripción. El relay de F2 pudo ser síncrono solo porque era de ms.

## Consequences

### Positivas
- El webhook responde a Meta en ms (encolar es barato); el turno lento corre aislado con CPU asignada.
- Durabilidad + reintentos + dead-letter **sin escribir lógica de cola propia**.
- La **concurrencia por cola** es el dial natural para no reventar los rate-limits del proveedor LLM ni el pool de Cloud SQL bajo un pico de inbound.
- Patrón reusable por cualquier trabajo lento futuro (auto-reply de otros canales, jobs de bots, etc.).

### Negativas / Trade-offs
- **+1 pieza de infra**: una cola Cloud Tasks por entorno + un endpoint interno autenticado (OIDC/shared-secret) + IAM (`roles/cloudtasks.enqueuer` en la SA de Cloud Run; SA invoker con permiso de invocar el servicio). Los workflows `deploy-backend-{qa,prod}.yml` suman los envs `CLOUD_TASKS_*` + `SERVICE_BASE_URL` + `BOT_DISPATCH_SECRET` (lección §9: toda Setting nueva con efecto runtime va al `--set-env-vars`).
- **At-least-once** ⇒ el dispatch debe ser **idempotente** por turno (no duplicar el outbound ni el BotEvent si Cloud Tasks reintrega). Se apoya en el UNIQUE `(conversation_id, turn_number)` de BotEvent + el chequeo de turno en curso.
- El smoke local (sqlite, sin GCP) **mockea** `cloud_tasks.enqueue_turn` y llama `dispatch_turn` directo; el QA E2E ejercita la cola real (lección §9: lo que el smoke mockea, el QA E2E lo caza).

### Lo que esto obliga
- `app/core/cloud_tasks.py` (cliente lazy + `enqueue_turn`), dep `google-cloud-tasks`.
- Endpoint top-level `POST /api/v1/bots/engine/dispatch` con verificación OIDC/shared-secret (NO RBAC) + `POST /engine/dispatch-manual` (RBAC `BOT_ENGINE_INVOKE`, debugging).
- Enganche aditivo en `conversations.webhook_processor.process_inbound`: `if conv.assignee_type=='bot': cloud_tasks.enqueue_turn(...)`.
- Provisionar la cola (`medisage-bot-turns` / `-qa`) + IAM en F3 (no en F0/F1).

## Referencias
- Ficha del módulo: [`docs/modules/bots/README.md`](../modules/bots/README.md) + [`backend.md`](../modules/bots/backend.md) (§ engine + cloud_tasks).
- [ADR-005](ADR-005-agnostic-bot-engine.md) — motor agnóstico; este ADR fija el *cómo se dispara* el turno (independiente de *dónde corre* el LLM).
- [ADR-011](ADR-011-firestore-message-stream-cqrs.md) — el relay síncrono de F2 y por qué `BackgroundTasks` no sirve en Cloud Run (mismo aprendizaje, aplicado acá al trabajo lento).
- Aprendizaje operativo: [[feedback-medisage-operational-lessons]] §9 (deploy/infra/async en Cloud Run).
