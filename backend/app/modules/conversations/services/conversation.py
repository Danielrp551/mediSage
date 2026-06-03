"""
Conversation service (control plane, ADR-011). F2 expone:
- `find_or_create_open`: idempotente; devuelve el hilo abierto de (person, channel) o crea
  uno NUEVO con AUTO-ASIGNACIÓN al dueño del lead de la Person (continuidad "mis leads =
  mis chats") con fallback a `unassigned` (bandeja compartida). Escribe el primer
  `ConversationAssignmentLog` + encola el `conversation_upsert` al outbox (espejo Firestore).
- `enqueue_conversation_upsert`: encola el espejo liviano del Conversation a Firestore
  (`conversations/{cid}`) con `allowed_reader_ids`. Lo llaman find_or_create_open,
  persist_inbound (cada inbound nuevo) y —en F3— take/release/close/reopen/mark_read.
- lecturas del inbox: `list_inbox` (bandeja global) + `get_detail` (+ assignment_history).

`allowed_reader_ids = [assignee_user_id]` cuando hay asesor asignado; los SUPERVISORES
(rol con `CONVERSATIONS_READ`) leen cualquier hilo vía el claim `can_read_all=true` del
Custom Token (ver `services/realtime.py`) → NO se materializan en `allowed_reader_ids`
(evita staleness + un join por cada mensaje en el hot path). Las Security Rules chequean
`can_read_all == true || uid in allowed_reader_ids` (ver `firestore.rules`).

Las acciones de handoff (take/release/close/reopen/mark_read) + outbound llegan en F3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
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
)
from app.modules.crm.repositories.lead_assignment import lead_assignment_repository
from app.modules.crm.repositories.person import person_repository as crm_person_repository
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


async def get_detail(db: AsyncSession, conversation_id: str) -> SingleResponse[ConversationDetail]:
    conv = await conversation_repository.get_by_id(db, conversation_id)
    if conv is None:
        raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
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
