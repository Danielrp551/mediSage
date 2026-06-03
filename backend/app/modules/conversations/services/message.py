"""
Message service (CQRS / ADR-011). El mensaje NO se escribe en Postgres: se encola en el
`message_outbox` (TX Postgres, atómico, idempotente por `id=mid`) y un relay lo replica a
Firestore con el Admin SDK. La lectura PRIMARIA del hilo es el cliente Firestore real-time
(`onSnapshot`); `list_messages` es solo un fallback server-side.

F2 (inbound + lectura):
- `persist_inbound`: encola `message_create` (el doc EXACTO a escribir en Firestore) +
  actualiza unread_count/last_message_* + encola `conversation_upsert`. Idempotente por
  `mid` (= wamid): el reenvío de Meta no incrementa unread (devuelve False).
- `relay_outbox` / `relay_outbox_in_new_session`: el relay del outbox → Firestore (tras el
  200 del webhook vía BackgroundTasks). El enqueue al outbox es durable; el RELAY automático
  de filas `failed` (sweep/Cloud Task con backoff) es trabajo de infra/F3 — en F2 una fila
  `failed` NO se reintenta sola.
- `list_messages`: fallback de lectura del hilo (lee Firestore vía Admin SDK; SSR/degradación).

F3 (outbound + statuses):
- `send_outbound`: envío REAL contra Meta (Graph API vía `whatsapp.send_text`/httpx) + persiste
  el mensaje en el outbox (durable, id=mid uuid) con su estado final (sent/failed) + denorm del
  conversation + `conversation_upsert`. SIEMPRE devuelve 200: un fallo de envío persiste el
  mensaje como `failed` (la UI reintenta = mensaje nuevo), NO 502. El RELAY síncrono a Firestore
  lo dispara el ROUTER (mismo patrón que el webhook; evita el ciclo de import con conversation).
- `apply_status`: statuses[] (delivered/read/failed) → patch DIRECTO del doc Firestore (best-effort).

Las escrituras a Firestore (lib `firebase_admin`, síncronas) se envuelven en `asyncio.to_thread`
para no bloquear el event loop. El smoke (sqlite) mockea los writers de `app.core.firestore`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.enums import (
    AssigneeType,
    ContentType,
    ConversationStatus,
    MessageDirection,
    MessageExternalStatus,
    SenderType,
)
from app.modules.conversations.models.conversation import Conversation
from app.modules.conversations.repositories.channel_account import channel_account_repository
from app.modules.conversations.repositories.conversation import conversation_repository
from app.modules.conversations.repositories.message_outbox import message_outbox_repository
from app.modules.conversations.schemas.message import (
    MessageAttachmentItem,
    MessageItem,
    MessageSendRequest,
)
from app.modules.conversations.services import channel_account as channel_account_service
from app.modules.conversations.services import conversation as conversation_service
from app.modules.crm.repositories.person import person_repository as crm_person_repository
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = conversation_service.SYSTEM_USER_ID


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _doc_to_message_item(
    doc: dict[str, Any], *, sender_user: UserAuditInfo | None = None
) -> MessageItem:
    """Mapea un doc Firestore (snake_case, timestamps ISO) a `MessageItem`. `created_at`
    del doc → `created_on` del schema. Pydantic coerciona las ISO strings a datetime."""
    return MessageItem(
        id=doc["id"],
        conversation_id=doc["conversation_id"],
        direction=doc["direction"],
        sender_type=doc["sender_type"],
        sender_user_id=doc.get("sender_user_id"),
        sender_user=sender_user,
        content_type=doc["content_type"],
        content=doc.get("content"),
        external_id=doc.get("external_id"),
        external_status=doc.get("external_status"),
        sent_at=doc["sent_at"],
        delivered_at=doc.get("delivered_at"),
        read_at=doc.get("read_at"),
        failed_at=doc.get("failed_at"),
        failure_reason=doc.get("failure_reason"),
        attachments=[MessageAttachmentItem(**a) for a in doc.get("attachments", [])],
        created_on=doc.get("created_at") or doc.get("created_on"),
    )


async def persist_inbound(
    db: AsyncSession,
    *,
    conversation: Conversation,
    mid: str,
    content: str | None,
    content_type: ContentType,
    sent_at: datetime,
) -> bool:
    """Persiste un mensaje ENTRANTE en el control plane (TX Postgres) como op del outbox.
    IDEMPOTENTE por `mid` (= wamid; el `enqueue` hace ON CONFLICT (id) DO NOTHING): si ya
    estaba → no-op (False, el webhook NO incrementa unread). Si es nuevo: encola
    `message_create` (el doc a escribir en Firestore) + `conversation_upsert` + actualiza
    unread_count/last_message_*. NO escribe Firestore acá (eso lo hace relay_outbox, fuera
    de la tx). NO toca crm (sin MESSAGE_SENT — decisión §1)."""
    now = utc_now()
    doc: dict[str, Any] = {
        "id": mid,
        "conversation_id": conversation.id,
        "direction": MessageDirection.inbound.value,
        "sender_type": SenderType.contact.value,
        "sender_user_id": None,
        "bot_configuration_id": None,
        "content_type": content_type.value,
        "content": content,
        "external_id": mid,
        "external_status": None,
        "sent_at": _iso(sent_at),
        "delivered_at": None,
        "read_at": None,
        "failed_at": None,
        "failure_reason": None,
        "attachments": [],
        "created_at": _iso(now),
    }
    inserted = await message_outbox_repository.enqueue(
        db,
        id=mid,
        conversation_id=conversation.id,
        op="message_create",
        payload=doc,
        actor_id=SYSTEM_USER_ID,
    )
    if not inserted:
        return False  # reenvío de Meta → ya procesado
    conversation.unread_count += 1
    conversation.last_message_at = sent_at
    conversation.last_message_preview = (content or "")[:255]
    conversation.updated_by = SYSTEM_USER_ID
    conversation.updated_on = now
    # Espejo del conversation doc en Firestore (preview/unread/assignee/allowed_reader_ids).
    await conversation_service.enqueue_conversation_upsert(
        db, conversation, actor_id=SYSTEM_USER_ID
    )
    return True


async def relay_outbox(db: AsyncSession, *, limit: int = 100) -> int:
    """RELAY: lee message_outbox pendientes y los escribe a Firestore con el Admin SDK.
    Idempotente por doc-id (`set(doc_id)` create-if-absent/overwrite). Marca `done`; en error
    marca `failed` (`attempts`/`last_error` para diagnóstico). ⚠ En F2 una fila `failed` NO
    vuelve a barrerse (`list_pending` solo mira `pending`): el reintento automático
    (sweep/Cloud Task con backoff por `attempts`) es trabajo de infra/F3. El enqueue al outbox
    SÍ es durable (el row no se pierde); reprocesar un `done` no duplica (set idempotente)."""
    from app.core import firestore

    pending = await message_outbox_repository.list_pending(db, limit=limit)
    relayed = 0
    for row in pending:
        try:
            if row.op == "message_create":
                await asyncio.to_thread(
                    firestore.write_message_doc, row.conversation_id, row.payload
                )
            elif row.op == "conversation_upsert":
                await asyncio.to_thread(
                    firestore.upsert_conversation_doc, row.conversation_id, row.payload
                )
            elif row.op == "message_status":
                await asyncio.to_thread(
                    firestore.update_message_status, row.conversation_id, row.payload
                )
            await message_outbox_repository.mark_done(db, row.id)
            relayed += 1
        except Exception as exc:  # red / permisos Firestore → failed (reintento futuro)
            await message_outbox_repository.mark_failed(db, row.id, error=str(exc))
            logger.warning(
                "outbox relay failed",
                extra={"outbox_id": row.id, "op": row.op, "error": str(exc)},
            )
    await db.flush()
    return relayed


async def relay_outbox_in_new_session() -> int:
    """Wrapper para BackgroundTasks: abre su propia AsyncSession (la del request ya se cerró
    tras el response) y commitea. El COMMIT del control plane ocurre ANTES de que corra el
    background task (el cleanup de get_db precede al envío de la respuesta → los outbox rows
    ya están commiteados y visibles para esta sesión nueva)."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        relayed = await relay_outbox(db)
        await db.commit()
        return relayed


async def apply_status(
    *, conversation_id: str | None, external_id: str, status: str, ts: datetime
) -> None:
    """statuses[] del webhook (delivered/read/failed) → patch DIRECTO del doc Firestore
    (real-time; NO toca Postgres — el status es best-effort). No-op si el mensaje no existe
    (status de un mensaje que no enviamos). En el MVP F2 (sin outbound) suele ser no-op."""
    from app.core import firestore

    field = {"delivered": "delivered_at", "read": "read_at", "failed": "failed_at"}.get(status)
    patch: dict[str, Any] = {"external_id": external_id, "external_status": status}
    if field is not None:
        patch[field] = _iso(ts)
    await asyncio.to_thread(firestore.update_message_status, conversation_id, patch)


async def list_messages(
    db: AsyncSession,
    conversation_id: str,
    query: QueryRequest,
    *,
    actor_id: str,
    can_read_all: bool,
) -> PaginatedResponse[MessageItem]:
    """FALLBACK server-side (SSR / cliente sin Firestore): lee
    conversations/{cid}/messages del Admin SDK (orderBy created_at), pagina, hidrata
    sender_user (UserAuditInfo) y mapea cada doc a MessageItem. El path PRIMARIO es el
    cliente Firestore real-time (onSnapshot). SCOPING (anti-IDOR): el Admin SDK BYPASSA las
    Security Rules, así que el scoping del hilo ajeno se impone acá — quien solo tiene
    MY_CONVERSATIONS_READ (can_read_all=False) solo lee los mensajes de un hilo asignado a sí
    mismo (mismo 404 que `_assert_can_access` del browser real-time vía allowed_reader_ids)."""
    from app.core import firestore

    conv = await conversation_repository.get_by_id(db, conversation_id)
    if conv is None:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
    conversation_service._assert_can_access(conv, actor_id=actor_id, can_read_all=can_read_all)
    docs, total = await asyncio.to_thread(
        firestore.list_message_docs,
        conversation_id,
        skip=query.pagination.skip,
        limit=query.pagination.limit,
    )
    sender_ids = {d["sender_user_id"] for d in docs if d.get("sender_user_id")}
    audit = await user_repository.get_audit_info_map(db, sender_ids)
    items: list[MessageItem] = []
    for d in docs:
        sid = d.get("sender_user_id")
        actor = audit.get(sid) if sid is not None else None
        sender = (
            UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)
            if actor is not None
            else None
        )
        items.append(_doc_to_message_item(d, sender_user=sender))
    return PaginatedResponse(
        data=PaginatedData(
            items=items,
            total=total,
            skip=query.pagination.skip,
            limit=query.pagination.limit,
        )
    )


async def send_outbound(
    db: AsyncSession,
    conversation_id: str,
    payload: MessageSendRequest,
    *,
    actor_id: str,
) -> SingleResponse[MessageItem]:
    """OUTBOUND real (F3). Valida (hilo abierto + actor=asignado + texto), envía a Meta vía
    `whatsapp.send_text` (httpx) y persiste el mensaje en el outbox (durable, id=mid uuid)
    con su estado FINAL (sent + external_id=wamid, o failed + failure_reason) + denormaliza
    el conversation + encola `conversation_upsert`. SIEMPRE 200: un fallo de envío
    (credenciales / sin destinatario / 4xx-5xx / red) persiste el mensaje `failed` (la UI
    reintenta = mensaje nuevo), NO 502. El RELAY síncrono a Firestore lo dispara el ROUTER.
    """
    # Lazy import: `whatsapp` importa este módulo (message) → evitar el ciclo al import-time.
    from app.modules.conversations.services.webhook_processor import whatsapp as wa

    conv = await conversation_repository.get_by_id(db, conversation_id)
    if conv is None:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
    if conv.status != ConversationStatus.open.value:
        raise BadRequestException("La conversación está cerrada", code="CONVERSATION_NOT_OPEN")
    # Autorización de negocio: solo el asesor ASIGNADO puede enviar (el RBAC ya exigió
    # MESSAGES_SEND en el router). Un supervisor debe tomar el hilo primero.
    if conv.assignee_type != AssigneeType.advisor.value or conv.assignee_user_id != actor_id:
        raise ForbiddenException(
            "No eres el asesor asignado a esta conversación", code="NOT_CONVERSATION_ASSIGNEE"
        )
    if payload.content_type != ContentType.text:
        raise BadRequestException(
            "Solo se admite texto en esta versión", code="UNSUPPORTED_CONTENT_TYPE"
        )

    settings = get_settings()
    now = utc_now()
    mid = generate_uuid()
    external_id: str | None = None
    external_status = MessageExternalStatus.sent.value
    failed_at: str | None = None
    failure_reason: str | None = None

    # Envío REAL a Meta. CUALQUIER fallo (cuenta borrada / sin destinatario / credenciales /
    # 4xx-5xx / red) → persistir el mensaje `failed` y devolver 200 (la UI reintenta). NO 502.
    ca = await channel_account_repository.get_by_id(db, conv.channel_account_id)
    try:
        if ca is None:
            raise ValueError("La cuenta de canal ya no existe")
        recipient = (
            await crm_person_repository.get_channel_identifier(db, conv.person_id, ca.channel_type)
            if conv.person_id is not None
            else None
        )
        if recipient is None:
            raise ValueError("No hay un identificador de WhatsApp para el contacto")
        creds = await channel_account_service.get_credentials(db, ca)
        external_id = await wa.send_text(
            access_token=creds["access_token"],
            phone_number_id=creds.get("phone_number_id") or (ca.phone_number_id or ""),
            to=recipient.identifier,
            body=payload.content,
            graph_api_version=settings.WHATSAPP_GRAPH_API_VERSION,
        )
    except Exception as exc:  # noqa: BLE001 — el outbound fallido se persiste (200), no 502
        external_status = MessageExternalStatus.failed.value
        failed_at = _iso(now)
        failure_reason = str(exc)[:255]
        logger.warning(
            "outbound send failed",
            extra={"conversation_id": conv.id, "error": str(exc)},
        )

    doc: dict[str, Any] = {
        "id": mid,
        "conversation_id": conv.id,
        "direction": MessageDirection.outbound.value,
        "sender_type": SenderType.advisor.value,
        "sender_user_id": actor_id,
        "bot_configuration_id": None,
        "content_type": ContentType.text.value,
        "content": payload.content,
        "external_id": external_id,
        "external_status": external_status,
        "sent_at": _iso(now),
        "delivered_at": None,
        "read_at": None,
        "failed_at": failed_at,
        "failure_reason": failure_reason,
        "attachments": [],
        "created_at": _iso(now),
    }
    # Durable (id=mid uuid; idempotente por PK). El relay (router) lo proyecta a Firestore.
    await message_outbox_repository.enqueue(
        db, id=mid, conversation_id=conv.id, op="message_create", payload=doc, actor_id=actor_id
    )
    # Denorm del conversation para el inbox (el mensaje existe en el hilo aun si falló el envío).
    conv.last_message_at = now
    conv.last_message_preview = payload.content[:255]
    conv.updated_by = actor_id
    conv.updated_on = now
    await conversation_service.enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    await db.flush()

    audit = await user_repository.get_audit_info_map(db, {actor_id})
    actor = audit.get(actor_id)
    sender = (
        UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)
        if actor is not None
        else None
    )
    return SingleResponse(data=_doc_to_message_item(doc, sender_user=sender))
