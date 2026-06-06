"""
Conversation service (control plane, ADR-011). F2 expone:
- `find_or_create_open`: idempotente; devuelve el hilo abierto de (person, channel) o crea
  uno NUEVO con AUTO-ASIGNACIÓN al dueño del lead de la Person (continuidad "mis leads =
  mis chats") con fallback a `unassigned` (bandeja compartida). Escribe el primer
  `ConversationAssignmentLog` + encola el `conversation_upsert` al outbox (espejo Firestore).
- `enqueue_conversation_upsert`: encola el espejo liviano del Conversation a Firestore
  (`conversations/{cid}`) con `allowed_reader_ids`. Lo llaman find_or_create_open,
  persist_inbound (cada inbound nuevo) y —en F3— take/release/close/reopen/mark_read.
- lecturas del inbox: `list_inbox` (bandeja global) + `list_my_inbox` (mi bandeja,
  assignee=actor) + `get_detail` (+ assignment_history).
- acciones de handoff (F3): `take`/`release`/`close`/`reopen`/`mark_read` — mutan el estado
  relacional + el `ConversationAssignmentLog` (audit inmutable, una sola fila vigente vía
  `_close_current_log`/`_open_assignment_log`/`_reassign`) + encolan `conversation_upsert`
  (refleja status/assignee/allowed_reader_ids/unread en Firestore — la pieza que gobierna
  las Security Rules del hilo). `take`/`release` además emiten `CONVERSATION_TAKEN`/
  `CONVERSATION_RELEASED` a la timeline de crm (`crm.lead_activity.log`, audit inmutable —
  esos tipos NO son ADVISOR_ACTIVITY_TYPES). El RELAY síncrono del outbox lo dispara el
  router (mismo patrón que el webhook), NO el service (evita el ciclo de import con message).

`allowed_reader_ids = [assignee_user_id]` cuando hay asesor asignado; los SUPERVISORES
(rol con `CONVERSATIONS_READ`) leen cualquier hilo vía el claim `can_read_all=true` del
Custom Token (ver `services/realtime.py`) → NO se materializan en `allowed_reader_ids`
(evita staleness + un join por cada mensaje en el hot path). Las Security Rules chequean
`can_read_all == true || uid in allowed_reader_ids` (ver `firestore.rules`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.enums import AssigneeType, ConversationStatus
from app.modules.conversations.models.channel_account import ChannelAccount
from app.modules.conversations.models.conversation import Conversation
from app.modules.conversations.models.conversation_assignment_log import (
    ConversationAssignmentLog,
)
from app.modules.conversations.repositories.channel_account import channel_account_repository
from app.modules.conversations.repositories.conversation import conversation_repository
from app.modules.conversations.repositories.conversation_assignment_log import (
    conversation_assignment_log_repository,
)
from app.modules.conversations.repositories.message_outbox import message_outbox_repository
from app.modules.conversations.schemas.channel_account import ChannelAccountOption
from app.modules.conversations.schemas.conversation import (
    ConversationAssignmentLogItem,
    ConversationDetail,
    ConversationListItem,
    ReleaseConversationRequest,
)
from app.modules.crm.enums import ActivityType
from app.modules.crm.repositories.lead_assignment import lead_assignment_repository
from app.modules.crm.repositories.person import person_repository as crm_person_repository
from app.modules.crm.services import lead_activity as crm_lead_activity
from app.modules.crm.services import person as crm_person
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now

SYSTEM_USER_ID = crm_person.SYSTEM_USER_ID


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _iso(dt: datetime | None) -> str | None:
    """ISO 8601 con offset (UTC). El payload del outbox es JSONB (no acepta datetime); el
    contrato del front declara estos campos como string ISO; orderBy ISO-UTC en Firestore
    ordena cronológicamente."""
    return dt.isoformat() if dt is not None else None


# ── Espejo del Conversation a Firestore (outbox conversation_upsert) ─────────────


async def enqueue_conversation_upsert(
    db: AsyncSession, conv: Conversation, *, actor_id: str
) -> None:
    """Encola el espejo liviano del Conversation a Firestore (`conversations/{cid}`). El
    relay lo escribe con `upsert_conversation_doc` (set/merge por cid, idempotente).
    `allowed_reader_ids = [assignee]` (los supervisores leen vía can_read_all del token)."""
    reader_ids: list[str] = []
    if conv.assignee_type == AssigneeType.advisor.value and conv.assignee_user_id:
        reader_ids = [conv.assignee_user_id]
    person_name: str | None = None
    if conv.person_id is not None:
        person = await crm_person_repository.get_by_id(db, conv.person_id)
        if person is not None:
            person_name = (
                f"{person.first_name} {person.last_name} {person.second_last_name or ''}".strip()
            )
    doc: dict[str, Any] = {
        "status": conv.status,
        "assignee_type": conv.assignee_type,
        "assignee_user_id": conv.assignee_user_id,
        "allowed_reader_ids": reader_ids,
        "channel_account_id": conv.channel_account_id,
        "person_id": conv.person_id,
        "person_name": person_name,
        "last_message_at": _iso(conv.last_message_at),
        "last_message_preview": conv.last_message_preview,
        "unread_count": conv.unread_count,
        "updated_at": _iso(utc_now()),
    }
    await message_outbox_repository.enqueue(
        db,
        id=generate_uuid(),
        conversation_id=conv.id,
        op="conversation_upsert",
        payload=doc,
        actor_id=actor_id,
    )


async def _open_assignment_log(
    db: AsyncSession,
    conv: Conversation,
    *,
    from_type: AssigneeType | None,
    from_user: str | None,
    to_type: AssigneeType,
    to_user: str | None,
    by_actor: str | None,
    reason: str | None,
    now: datetime,
) -> None:
    """Abre una nueva fila vigente del historial de handoff (ended_at=NULL). `by_actor`
    NULL = cambio automático (auto-asignación). created_by/updated_by caen a SYSTEM si no
    hay actor humano."""
    audit_actor = by_actor or SYSTEM_USER_ID
    db.add(
        ConversationAssignmentLog(
            id=generate_uuid(),
            conversation_id=conv.id,
            from_assignee_type=(from_type.value if from_type is not None else None),
            from_assignee_user_id=from_user,
            to_assignee_type=to_type.value,
            to_assignee_user_id=to_user,
            started_at=now,
            ended_at=None,
            by_actor_user_id=by_actor,
            reason=reason,
            active=True,
            created_by=audit_actor,
            created_on=now,
            updated_by=audit_actor,
            updated_on=now,
        )
    )


async def find_or_create_open(
    db: AsyncSession,
    *,
    person_id: str,
    channel_account: ChannelAccount,
    actor_id: str = SYSTEM_USER_ID,
) -> Conversation:
    """Idempotente: devuelve el hilo abierto de (person, channel) si existe; si no, crea
    uno NUEVO con auto-asignación al dueño del lead de la Person (fallback unassigned)."""
    open_conv = await conversation_repository.get_open(db, person_id, channel_account.id)
    if open_conv is not None:
        return open_conv
    now = utc_now()
    # AUTO-ASIGNACIÓN: el dueño del lead vía crm (lectura aditiva, sin cambio a crm).
    advisor_map = await lead_assignment_repository.advisor_map(db, [person_id])
    advisor_id = advisor_map.get(person_id)
    if advisor_id is not None:
        assignee_type, assignee_user_id = AssigneeType.advisor, advisor_id
    else:
        assignee_type, assignee_user_id = AssigneeType.unassigned, None
    conv = Conversation(
        id=generate_uuid(),
        channel_account_id=channel_account.id,
        person_id=person_id,
        status=ConversationStatus.open.value,
        assignee_type=assignee_type.value,
        assignee_user_id=assignee_user_id,
        opened_at=now,
        unread_count=0,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(conv)
    await db.flush()  # materializa conv.id para el log + el outbox
    await _open_assignment_log(
        db,
        conv,
        from_type=None,
        from_user=None,
        to_type=assignee_type,
        to_user=assignee_user_id,
        by_actor=None,  # auto
        reason="Auto-asignación",
        now=now,
    )
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    await db.flush()
    return conv


# ── Lecturas del inbox (read-only F2) ────────────────────────────────────────────


def _collect_assignee_ids(rows: list[Conversation]) -> set[str]:
    return {c.assignee_user_id for c in rows if c.assignee_user_id is not None}


async def _to_list_items(db: AsyncSession, rows: list[Conversation]) -> list[ConversationListItem]:
    channel_map = await channel_account_repository.get_by_ids(
        db, [c.channel_account_id for c in rows]
    )
    person_ids = [c.person_id for c in rows if c.person_id is not None]
    person_map = await crm_person.person_option_map(db, person_ids)
    audit_users = await user_repository.get_audit_info_map(db, _collect_assignee_ids(rows))
    items: list[ConversationListItem] = []
    for c in rows:
        channel = channel_map.get(c.channel_account_id)
        items.append(
            ConversationListItem(
                id=c.id,
                channel_account=ChannelAccountOption.model_validate(channel, from_attributes=True),
                person=(person_map.get(c.person_id) if c.person_id is not None else None),
                status=ConversationStatus(c.status),
                assignee_type=AssigneeType(c.assignee_type),
                assignee_user=(
                    _audit_info(audit_users.get(c.assignee_user_id))
                    if c.assignee_user_id is not None
                    else None
                ),
                last_message_preview=c.last_message_preview,
                last_message_at=c.last_message_at,
                unread_count=c.unread_count,
                created_on=c.created_on,
            )
        )
    return items


async def list_inbox(
    db: AsyncSession,
    query_request: QueryRequest,
    *,
    channel_account_id: str | None = None,
    status: str | None = None,
    assignee_user_id: str | None = None,
    unassigned: bool | None = None,
) -> PaginatedResponse[ConversationListItem]:
    rows, total = await conversation_repository.list_inbox(
        db,
        query_request,
        channel_account_id=channel_account_id,
        status=status,
        assignee_user_id=assignee_user_id,
        unassigned=unassigned,
    )
    return PaginatedResponse(
        data=PaginatedData(
            items=await _to_list_items(db, rows),
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


def _assert_can_access(conv: Conversation, *, actor_id: str | None, can_read_all: bool) -> None:
    """Scoping de lectura de UN hilo (RBAC server-side, defensa contra IDOR): quien tiene
    `CONVERSATIONS_READ` (can_read_all=bandeja global/supervisor) lee cualquiera; quien solo
    tiene `MY_CONVERSATIONS_READ` solo el que tiene asignado. Devuelve el MISMO 404 que
    "no encontrado" (no filtra la existencia). Los callers INTERNOS (acciones ya autorizadas
    que recargan el detalle) usan can_read_all=True → no se scopea."""
    if not can_read_all and conv.assignee_user_id != actor_id:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")


async def get_detail(
    db: AsyncSession,
    conversation_id: str,
    *,
    actor_id: str | None = None,
    can_read_all: bool = True,
) -> SingleResponse[ConversationDetail]:
    conv = await conversation_repository.get_by_id(db, conversation_id)
    if conv is None:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
    _assert_can_access(conv, actor_id=actor_id, can_read_all=can_read_all)
    base = (await _to_list_items(db, [conv]))[0]
    logs = await conversation_assignment_log_repository.list_for_conversation(db, conv.id)
    log_actor_ids: set[str] = set()
    for log in logs:
        for uid in (log.from_assignee_user_id, log.to_assignee_user_id, log.by_actor_user_id):
            if uid is not None:
                log_actor_ids.add(uid)
    log_users = await user_repository.get_audit_info_map(db, log_actor_ids)
    history = [
        ConversationAssignmentLogItem(
            id=log.id,
            from_assignee_type=(
                AssigneeType(log.from_assignee_type) if log.from_assignee_type else None
            ),
            from_assignee_user=(
                _audit_info(log_users.get(log.from_assignee_user_id))
                if log.from_assignee_user_id is not None
                else None
            ),
            to_assignee_type=AssigneeType(log.to_assignee_type),
            to_assignee_user=(
                _audit_info(log_users.get(log.to_assignee_user_id))
                if log.to_assignee_user_id is not None
                else None
            ),
            started_at=log.started_at,
            ended_at=log.ended_at,
            by_actor_user=(
                _audit_info(log_users.get(log.by_actor_user_id))
                if log.by_actor_user_id is not None
                else None
            ),
            reason=log.reason,
        )
        for log in logs
    ]
    detail = ConversationDetail(
        **base.model_dump(),
        bot_configuration_id=conv.bot_configuration_id,
        opened_at=conv.opened_at,
        closed_at=conv.closed_at,
        assignment_history=history,
    )
    return SingleResponse(data=detail)


async def list_my_inbox(
    db: AsyncSession,
    query_request: QueryRequest,
    *,
    actor_id: str,
    channel_account_id: str | None = None,
    status: str | None = None,
) -> PaginatedResponse[ConversationListItem]:
    """Mi bandeja: las conversaciones cuyo assignee advisor = el actor del token. Reusa
    `list_inbox` forzando `assignee_user_id=actor_id` (el filtro "sin asignar" no aplica
    en este scope). Gateado en el router por `MY_CONVERSATIONS_READ`."""
    return await list_inbox(
        db,
        query_request,
        channel_account_id=channel_account_id,
        status=status,
        assignee_user_id=actor_id,
        unassigned=None,
    )


# ── Acciones de handoff (F3) ──────────────────────────────────────────────────────


async def _get_or_404(db: AsyncSession, conversation_id: str) -> Conversation:
    conv = await conversation_repository.get_by_id(db, conversation_id)
    if conv is None:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
    return conv


async def _close_current_log(
    db: AsyncSession, conversation_id: str, *, now: datetime, actor_id: str | None
) -> None:
    """Cierra la fila vigente del historial (`ended_at=now`). `actor_id` None (cambio
    automático) cae a SYSTEM para la auditoría del UPDATE."""
    await conversation_assignment_log_repository.close_current(
        db, conversation_id, ended_at=now, actor_id=actor_id or SYSTEM_USER_ID
    )


async def _reassign(
    db: AsyncSession,
    conv: Conversation,
    *,
    to_type: AssigneeType,
    to_user: str | None,
    by_actor: str | None,
    reason: str | None,
    now: datetime,
) -> None:
    """Cierra el log vigente y abre uno nuevo, tomando el `from_*` del estado ACTUAL de la
    conversación (leer ANTES de que el caller mute conv.assignee_*). Materializa el
    invariante "una sola fila vigente"."""
    await _close_current_log(db, conv.id, now=now, actor_id=by_actor)
    await _open_assignment_log(
        db,
        conv,
        from_type=AssigneeType(conv.assignee_type),
        from_user=conv.assignee_user_id,
        to_type=to_type,
        to_user=to_user,
        by_actor=by_actor,
        reason=reason,
        now=now,
    )


async def take(
    db: AsyncSession, conversation_id: str, *, actor_id: str, reason: str | None = None
) -> SingleResponse[ConversationDetail]:
    """El asesor se asigna la conversación (assignee=advisor=actor). Cierra el log vigente +
    abre uno nuevo, pone unread=0 (tomar = leer), emite CONVERSATION_TAKEN a crm y refleja
    el nuevo assignee/allowed_reader_ids en Firestore (conversation_upsert). Solo sobre un hilo
    ABIERTO (un hilo cerrado se reabre primero) — evita dejar un ConversationAssignmentLog
    vigente sobre un hilo cerrado (que un reopen posterior duplicaría)."""
    conv = await _get_or_404(db, conversation_id)
    if conv.status != ConversationStatus.open.value:
        raise BadRequestException("La conversación está cerrada", code="CONVERSATION_NOT_OPEN")
    now = utc_now()
    await _reassign(
        db,
        conv,
        to_type=AssigneeType.advisor,
        to_user=actor_id,
        by_actor=actor_id,
        reason=reason,
        now=now,
    )
    conv.assignee_type = AssigneeType.advisor.value
    conv.assignee_user_id = actor_id
    conv.unread_count = 0
    conv.updated_by = actor_id
    conv.updated_on = now
    if conv.person_id is not None:
        await crm_lead_activity.log(
            db,
            conv.person_id,
            ActivityType.CONVERSATION_TAKEN,
            advisor_user_id=actor_id,
            actor_id=actor_id,
            related_conversation_id=conv.id,
            payload={"channel_account_id": conv.channel_account_id},
        )
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    await db.flush()
    return await get_detail(db, conv.id)


async def release(
    db: AsyncSession,
    conversation_id: str,
    payload: ReleaseConversationRequest,
    *,
    actor_id: str,
) -> SingleResponse[ConversationDetail]:
    """Libera la conversación a `unassigned` (o `bot` si bots existiera). Solo el asesor
    ASIGNADO puede liberar (consistente con el composer/send y con la UI, que solo ofrece
    "Liberar" al asignado; un supervisor reasigna vía take). Solo sobre un hilo ABIERTO.
    `advisor` → INVALID_ASSIGNEE (para asignar a un asesor se usa `take`). Emite
    CONVERSATION_RELEASED."""
    conv = await _get_or_404(db, conversation_id)
    if conv.status != ConversationStatus.open.value:
        raise BadRequestException("La conversación está cerrada", code="CONVERSATION_NOT_OPEN")
    if conv.assignee_type != AssigneeType.advisor.value or conv.assignee_user_id != actor_id:
        raise ForbiddenException(
            "No eres el asesor asignado a esta conversación", code="NOT_CONVERSATION_ASSIGNEE"
        )
    if payload.to_assignee_type == AssigneeType.advisor:
        raise BadRequestException("Para asignar a un asesor usa 'Tomar'", code="INVALID_ASSIGNEE")
    if payload.to_assignee_type == AssigneeType.bot and payload.to_bot_configuration_id is None:
        # release→bot (bots #6, F3): exige el bot a asignar. La forward FK (migr 0017) valida que el
        # id exista; el dispatch valida la versión vigente (NO_CURRENT_VERSION). El bot reactivado
        # responde en su próximo turno (auto-enqueue por webhook = F3b; manual vía dispatch-manual).
        raise BadRequestException("Falta la configuración de bot", code="INVALID_ASSIGNEE")
    now = utc_now()
    await _reassign(
        db,
        conv,
        to_type=payload.to_assignee_type,
        to_user=None,
        by_actor=actor_id,
        reason=payload.reason,
        now=now,
    )
    conv.assignee_type = payload.to_assignee_type.value
    conv.assignee_user_id = None
    conv.bot_configuration_id = (
        payload.to_bot_configuration_id if payload.to_assignee_type == AssigneeType.bot else None
    )
    conv.updated_by = actor_id
    conv.updated_on = now
    if conv.person_id is not None:
        await crm_lead_activity.log(
            db,
            conv.person_id,
            ActivityType.CONVERSATION_RELEASED,
            advisor_user_id=actor_id,
            actor_id=actor_id,
            related_conversation_id=conv.id,
            payload={"to_assignee_type": payload.to_assignee_type.value},
        )
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    await db.flush()
    return await get_detail(db, conv.id)


async def close(
    db: AsyncSession, conversation_id: str, *, actor_id: str
) -> SingleResponse[ConversationDetail]:
    """Cierra el hilo (status='closed'; NO soft-delete — la traza queda y se puede reabrir).
    Cierra el log de handoff vigente. Idempotente si ya estaba cerrado."""
    conv = await _get_or_404(db, conversation_id)
    if conv.status == ConversationStatus.closed.value:
        return await get_detail(db, conv.id)
    now = utc_now()
    conv.status = ConversationStatus.closed.value
    conv.closed_at = now
    conv.updated_by = actor_id
    conv.updated_on = now
    await _close_current_log(db, conv.id, now=now, actor_id=actor_id)
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    await db.flush()
    return await get_detail(db, conv.id)


async def reopen(
    db: AsyncSession, conversation_id: str, *, actor_id: str
) -> SingleResponse[ConversationDetail]:
    """Reabre un hilo cerrado (status='open'). Guard: no puede haber OTRA conversación
    abierta para el mismo (person, channel) → 409 CONVERSATION_ALREADY_OPEN (respeta el
    UNIQUE parcial 1-open). Idempotente si ya estaba abierto (evita duplicar la fila vigente
    del historial). Abre un nuevo log vigente con el assignee actual (no resetea asignación)."""
    conv = await _get_or_404(db, conversation_id)
    if conv.status == ConversationStatus.open.value:
        return await get_detail(db, conv.id)  # idempotente: NO abrir un 2º log vigente
    if conv.person_id is not None and await conversation_repository.has_other_open(
        db, conv.person_id, conv.channel_account_id, conv.id
    ):
        raise ConflictException(
            "Ya hay una conversación abierta para este contacto en este canal",
            code="CONVERSATION_ALREADY_OPEN",
        )
    now = utc_now()
    conv.status = ConversationStatus.open.value
    conv.closed_at = None
    conv.updated_by = actor_id
    conv.updated_on = now
    await _open_assignment_log(
        db,
        conv,
        from_type=None,
        from_user=None,
        to_type=AssigneeType(conv.assignee_type),
        to_user=conv.assignee_user_id,
        by_actor=actor_id,
        reason="Reapertura",
        now=now,
    )
    await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
    await db.flush()
    return await get_detail(db, conv.id)


async def mark_read(
    db: AsyncSession, conversation_id: str, *, actor_id: str, can_read_all: bool
) -> SingleResponse[ConversationDetail]:
    """Marca la conversación como leída (unread_count=0) y lo refleja en Firestore. NO toca
    la asignación ni el estado. Idempotente. SCOPING (defensa anti-IDOR): quien solo tiene
    MY_CONVERSATIONS_READ (can_read_all=False) solo puede marcar leído un hilo ASIGNADO a sí
    mismo → si no, 404 (no filtra existencia ni filtra el detalle de un hilo ajeno)."""
    conv = await _get_or_404(db, conversation_id)
    _assert_can_access(conv, actor_id=actor_id, can_read_all=can_read_all)
    if conv.unread_count != 0:
        conv.unread_count = 0
        conv.updated_by = actor_id
        conv.updated_on = utc_now()
        await enqueue_conversation_upsert(db, conv, actor_id=actor_id)
        await db.flush()
    return await get_detail(db, conv.id)
