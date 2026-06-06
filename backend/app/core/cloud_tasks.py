"""
Cloud Tasks: despacho ASÍNCRONO del turno del bot (ADR-012). El webhook de WhatsApp, tras su pipe
SÍNCRONO (control plane + relay a Firestore), ENCOLA una task que hace
`POST {SERVICE_BASE_URL}/api/v1/bots/engine/dispatch` → el motor (lento: LLM + tool-calling) corre con
CPU asignada, FUERA del request de Meta (timeout + cpu-throttling), con reintentos+backoff de la cola.
NO usa `BackgroundTasks` (no confiable en Cloud Run — ver memoria de conversations).

- Cliente LAZY `tasks_v2.CloudTasksAsyncClient` (no al import) → el boot local / smoke no carga el SDK.
- NO-OP si `ENV_NAME=='dev'` o `CLOUD_TASKS_QUEUE==''` (sin cola): local/smoke NUNCA tocan Cloud Tasks.
  El auto-path solo se activa en qa/prod con la cola provisionada.
- Auth del dispatch = shared-secret en el header `X-Bot-Dispatch-Secret` (== `BOT_DISPATCH_SECRET`, en
  Secret Manager por entorno; el endpoint lo compara en tiempo constante). Se eligió sobre OIDC porque
  el servicio es PÚBLICO (Meta/Vercel) → OIDC degradaría a verificación in-app (sin el rechazo de la
  plataforma) sumando fallas solo-en-prod (cert-fetch/clock-skew/drift de audiencia/IAM actAs); el
  shared-secret reusa el mismo `hmac.compare_digest` que el webhook de Meta ya corre en prod. OIDC =
  hardening futuro si el endpoint se separa a un Cloud Run privado propio (`--no-allow-unauthenticated`).
- DEDUPE (dos capas): (1) la task lleva un nombre DETERMINISTA derivado de (conversation_id,
  input_message_id) → un reintento del webhook de Meta del MISMO inbound reencola con el mismo nombre →
  Cloud Tasks lo rechaza (`AlreadyExists` = no-op). Esto deduplica el ENQUEUE, NO el at-least-once de la
  cola (una task YA aceptada se reintenta si el handler corrió pero el 2xx se perdió). (2) Por eso el
  CONSUMIDOR (`engine.dispatch_turn`) es idempotente por `input_message_id` (no re-ejecuta un turno ya
  registrado). Rotación del secret: una task encolada lleva el secret viejo horneado → drenar la cola o
  solapar dos secrets válidos durante la rotación (arista operativa; el siguiente inbound recupera).

`google-cloud-tasks` se importa LAZY (dentro de las funciones). Reusable por cualquier módulo futuro
con trabajo async vía Cloud Tasks.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Nombre del header del shared-secret. UNA sola fuente, importada por el enqueue (acá) y por el verify
# del endpoint /engine/dispatch → sin drift de nombre (gotcha de falla silenciosa en prod).
DISPATCH_SECRET_HEADER = "X-Bot-Dispatch-Secret"

# Ruta del dispatch bajo `Settings.API_V1_PREFIX` (target de la cola).
_DISPATCH_PATH = "/bots/engine/dispatch"

_client: Any = None  # lazy CloudTasksAsyncClient


def _get_client() -> Any:
    """Construye el cliente async del SDK en la primera llamada (no al import). Import diferido:
    `google-cloud-tasks` solo se necesita en Cloud Run; el boot local / smoke no lo carga."""
    global _client
    if _client is None:
        import google.cloud.tasks_v2 as tasks_v2

        _client = tasks_v2.CloudTasksAsyncClient()
    return _client


async def enqueue_turn(*, conversation_id: str, input_message_id: str | None) -> None:
    """Encola un turno del bot. NO-OP en dev o sin cola configurada. Un fallo de encolado se loguea y
    NO se propaga (el inbound ya es durable: outbox Postgres + doc Firestore; el 200 a Meta no se
    bloquea). El header `X-Bot-Dispatch-Secret` autentica el dispatch en el endpoint."""
    settings = get_settings()
    if settings.ENV_NAME == "dev" or not settings.CLOUD_TASKS_QUEUE:
        return
    try:
        import google.cloud.tasks_v2 as tasks_v2
        from google.api_core.exceptions import AlreadyExists

        client = _get_client()
        # rstrip('/'): SERVICE_BASE_URL con trailing slash (copy/paste de la consola Cloud Run) +
        # API_V1_PREFIX que ya empieza con '/' daría '//api/...' → 404 (4xx no reintentable) → turno
        # perdido en silencio. Normalizar acá evita esa falla solo-en-prod.
        url = f"{settings.SERVICE_BASE_URL.rstrip('/')}{settings.API_V1_PREFIX}{_DISPATCH_PATH}"
        body = json.dumps(
            {"conversation_id": conversation_id, "input_message_id": input_message_id}
        ).encode()
        task: dict[str, Any] = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {
                    "Content-Type": "application/json",
                    DISPATCH_SECRET_HEADER: settings.BOT_DISPATCH_SECRET,
                },
                "body": body,
            }
        }
        if input_message_id:
            # Nombre determinista: los nombres de Cloud Tasks solo admiten [a-zA-Z0-9_-]; el wamid
            # trae '.'/'='/'/' → se hashea. Mismo inbound (reintento de Meta) → mismo nombre → dedupe.
            digest = hashlib.sha256(f"{conversation_id}:{input_message_id}".encode()).hexdigest()
            task["name"] = client.task_path(
                settings.GCP_PROJECT_ID,
                settings.CLOUD_TASKS_LOCATION,
                settings.CLOUD_TASKS_QUEUE,
                digest,
            )
        parent = client.queue_path(
            settings.GCP_PROJECT_ID, settings.CLOUD_TASKS_LOCATION, settings.CLOUD_TASKS_QUEUE
        )
        try:
            await client.create_task(parent=parent, task=task)
        except AlreadyExists:
            logger.info("bot turn ya encolado (dedupe)", extra={"conversation_id": conversation_id})
    except Exception:  # noqa: BLE001 — encolar es best-effort; nunca romper el 200 del webhook
        logger.exception(
            "no se pudo encolar el turno del bot", extra={"conversation_id": conversation_id}
        )
