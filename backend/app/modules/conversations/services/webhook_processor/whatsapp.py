"""
Procesador del webhook de WhatsApp Cloud API. `verify_signature` valida la firma de Meta
(HMAC-SHA256 del body RAW con el app_secret, comparación en tiempo constante).
`process_inbound` parsea `entry[].changes[].value.{messages[], statuses[], contacts[]}`,
resuelve/crea la Person vía crm (hardened con advisory lock), abre/encuentra el hilo
(auto-asignación al dueño del lead) y encola cada mensaje en el outbox. Flujo SÍNCRONO
(MVP, sin bot lento); texto primero (media diferida a F4). El relay a Firestore corre tras
el 200 (BackgroundTasks).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.enums import ContentType
from app.modules.conversations.models.channel_account import ChannelAccount
from app.modules.conversations.services import conversation as conversation_service
from app.modules.conversations.services import message as message_service
from app.modules.crm.enums import ChannelType
from app.modules.crm.schemas.person import PersonCreate
from app.modules.crm.services import person as crm_person

logger = logging.getLogger(__name__)

# WhatsApp message type → ContentType del contrato. Los no listados caen a text.
_WA_TYPE_TO_CONTENT: dict[str, ContentType] = {
    "text": ContentType.text,
    "image": ContentType.image,
    "audio": ContentType.audio,
    "video": ContentType.video,
    "document": ContentType.document,
    "location": ContentType.location,
    "sticker": ContentType.sticker,
    "contacts": ContentType.contact_card,
}


def verify_signature(*, raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC_SHA256(app_secret, raw_body). Comparación en
    tiempo constante. raw_body = los bytes EXACTOS del body (Meta firma los bytes, no el JSON
    re-serializado)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + expected, signature_header)


def _ts(timestamp: Any) -> datetime:
    """Unix epoch (segundos, string o int) → datetime UTC. Fallback a ahora si falta."""
    if timestamp is None:
        return datetime.now(UTC)
    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (ValueError, TypeError, OverflowError):
        return datetime.now(UTC)


def _extract_content(m: dict[str, Any]) -> tuple[str | None, ContentType]:
    """Texto primero: type='text' → (body, text). Otros tipos → (caption si viene, su
    ContentType) SIN media (F4 cablea el download del binario)."""
    mtype = m.get("type", "text")
    content_type = _WA_TYPE_TO_CONTENT.get(mtype, ContentType.text)
    if mtype == "text":
        return (m.get("text", {}) or {}).get("body"), ContentType.text
    payload = m.get(mtype)
    caption = payload.get("caption") if isinstance(payload, dict) else None
    return caption, content_type


async def process_inbound(
    db: AsyncSession, *, payload: dict[str, Any], channel_account: ChannelAccount
) -> None:
    """Parse + orquestación SÍNCRONA del control plane (antes del 200). El relay a Firestore
    corre aparte (BackgroundTasks)."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            contacts = {c["wa_id"]: c for c in value.get("contacts", []) if "wa_id" in c}
            for m in value.get("messages", []):
                wa_id = m.get("from")
                if not wa_id or not m.get("id"):
                    continue
                pushname = (
                    (contacts.get(wa_id, {}).get("profile", {}) or {}).get("name") or ""
                ).strip()
                # 1) Resolver/crear la Person vía crm (hardened con advisory lock — §8.1).
                person = await crm_person.find_by_identifier_or_create(
                    db,
                    ChannelType.whatsapp,
                    wa_id,
                    profile=PersonCreate(
                        first_name=(pushname[:80] or "Contacto"),
                        last_name="(WhatsApp)",  # placeholder editable; last_name exige min_length=1
                        identifiers=[],  # find_by_identifier_or_create construye el suyo
                    ),
                    campaign_id=channel_account.default_campaign_id,
                )
                # 2) Hilo abierto (auto-asignación al dueño del lead / unassigned).
                conv = await conversation_service.find_or_create_open(
                    db, person_id=person.id, channel_account=channel_account
                )
                # 3) Texto primero: encola el message_create (+ conversation_upsert) en el
                #    outbox; IDEMPOTENTE por mid (= wamid). El relay lo escribe a Firestore.
                content, content_type = _extract_content(m)
                await message_service.persist_inbound(
                    db,
                    conversation=conv,
                    mid=m["id"],
                    content=content,
                    content_type=content_type,
                    sent_at=_ts(m.get("timestamp")),
                )
            for s in value.get("statuses", []):
                if not s.get("id"):
                    continue
                # Status callbacks = BEST-EFFORT. apply_status patchea el doc Firestore DIRECTO
                # (no toca Postgres). Va en try/except: una falla de Firestore en un status NO
                # debe abortar la TX de control plane ni perder los mensajes inbound ya
                # encolados en el outbox del mismo batch (review F2 MAJOR). En el MVP F2 (sin
                # outbound) suele ser no-op (no hay doc del mensaje que el status referencie).
                try:
                    await message_service.apply_status(
                        conversation_id=None,
                        external_id=s["id"],
                        status=s.get("status", ""),
                        ts=_ts(s.get("timestamp")),
                    )
                except Exception:  # noqa: BLE001 — best-effort; nunca romper el inbound durable
                    logger.warning(
                        "apply_status falló (best-effort, ignorado)",
                        extra={"external_id": s.get("id"), "status": s.get("status")},
                    )
