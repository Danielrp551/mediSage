"""
Webhooks TOP-LEVEL de los proveedores de mensajería (sin JWT). La autenticación es la
firma del proveedor (POST: HMAC-SHA256 del body RAW con el app_secret) / el verify token
(GET: challenge de Meta), NO el RBAC del template.

WhatsApp Cloud API:
- GET  /api/v1/webhooks/whatsapp/{channel_account_id} → Meta verification challenge.
- POST /api/v1/webhooks/whatsapp/{channel_account_id} → inbound messages + status callbacks.

CQRS (ADR-011): la TX de control plane (Postgres) corre SÍNCRONA y se commitea ANTES del
200 (durabilidad garantizada por el outbox); la proyección a Firestore (data plane) se
dispara con BackgroundTasks DESPUÉS del 200. El cleanup de `get_db` (commit) precede al
envío de la respuesta, así que el background task ve los outbox rows ya commiteados.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status

from app.core.dependencies import DBSession
from app.core.exceptions import ForbiddenException, NotFoundException
from app.modules.conversations.repositories.channel_account import channel_account_repository
from app.modules.conversations.services import channel_account as channel_account_service
from app.modules.conversations.services import message as message_service
from app.modules.conversations.services.webhook_processor import whatsapp as wa

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp/{channel_account_id}")
async def verify_whatsapp(
    channel_account_id: str,
    db: DBSession,
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Meta verification challenge: compara `hub.verify_token` con el de la cuenta y
    devuelve `hub.challenge` crudo (text/plain) o 403."""
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")
    if hub_mode != "subscribe" or hub_verify_token != (ca.webhook_verify_token or ""):
        raise ForbiddenException("Token de verificación inválido", code="WEBHOOK_SIGNATURE_INVALID")
    return Response(
        content=hub_challenge, media_type="text/plain"
    )  # Meta espera el challenge crudo


@router.post("/whatsapp/{channel_account_id}", status_code=status.HTTP_200_OK)
async def inbound_whatsapp(
    channel_account_id: str, request: Request, db: DBSession, background: BackgroundTasks
) -> dict[str, bool]:
    """Valida la firma `X-Hub-Signature-256` sobre el body RAW, procesa el inbound (TX
    Postgres síncrona) y agenda el relay del outbox → Firestore tras el 200."""
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None or not ca.active:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")
    raw = await request.body()  # bytes EXACTOS (Meta firma estos; no re-serializar)
    creds = await channel_account_service.get_credentials(db, ca)
    if not wa.verify_signature(
        raw_body=raw,
        signature_header=request.headers.get("X-Hub-Signature-256"),
        app_secret=creds["app_secret"],
    ):
        raise ForbiddenException("Firma del webhook inválida", code="WEBHOOK_SIGNATURE_INVALID")
    payload = json.loads(raw or b"{}")
    # TX Postgres (control plane), síncrona, antes del 200.
    await wa.process_inbound(db, payload=payload, channel_account=ca)
    # Relay del outbox → Firestore tras el 200 (data plane). El outbox es durable.
    background.add_task(message_service.relay_outbox_in_new_session)
    return {"success": True}
