"""
Conversation repository. `ALLOWED_FIELDS` = SOLO columnas reales de `conversation`
(lección hotfix `cd10c78` de staff): person full_name, channel name, assignee full_name
y last_message_preview son DENORMALIZADOS → NO van acá. Los deep-links del inbox
(`channel_account_id`/`status`/`assignee_user_id`/`unassigned`) los traduce `list_inbox`
a filtros sobre columnas reales (patrón `crm.person_repository.list_paginated_filtered`).
`defaultSort = last_message_at desc`.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.enums import AssigneeType, ConversationStatus
from app.modules.conversations.models.conversation import Conversation
from app.shared.base_repository import BaseRepository
from app.shared.base_schemas import QueryRequest
from app.shared.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sorting,
    build_count_query,
)


class ConversationRepository(BaseRepository[Conversation]):
    ALLOWED_FIELDS: set[str] = {
        "status",
        "assignee_type",
        "assignee_user_id",
        "channel_account_id",
        "last_message_at",
        "created_on",
        "unread_count",
    }

    def __init__(self) -> None:
        super().__init__(Conversation)

    async def get_open(
        self, db: AsyncSession, person_id: str, channel_account_id: str
    ) -> Conversation | None:
        """El hilo abierto de (person, channel) — el core de find_or_create_open."""
        result = await db.execute(
            select(Conversation).where(
                Conversation.person_id == person_id,
                Conversation.channel_account_id == channel_account_id,
                Conversation.status == ConversationStatus.open.value,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def has_other_open(
        self, db: AsyncSession, person_id: str, channel_account_id: str, exclude_id: str
    ) -> bool:
        """Guard de reopen (409 CONVERSATION_ALREADY_OPEN): ¿hay OTRA open para el mismo
        (person, channel) distinta de exclude_id? (consumido en F3)."""
        result = await db.execute(
            select(Conversation.id).where(
                Conversation.person_id == person_id,
                Conversation.channel_account_id == channel_account_id,
                Conversation.status == ConversationStatus.open.value,
                Conversation.deleted_at.is_(None),
                Conversation.id != exclude_id,
            )
        )
        return result.scalars().first() is not None

    async def list_inbox(
        self,
        db: AsyncSession,
        query_request: QueryRequest,
        *,
        channel_account_id: str | None = None,
        status: str | None = None,
        assignee_user_id: str | None = None,
        unassigned: bool | None = None,
    ) -> tuple[list[Conversation], int]:
        """Inbox global. Aplica los deep-links como filtros sobre columnas REALES antes de
        delegar el sort/paginado a la maquinaria de QueryRequest (ALLOWED_FIELDS). Mismo
        molde que `crm.person_repository.list_paginated_filtered`."""
        conditions: list[ColumnElement[bool]] = []
        if channel_account_id is not None:
            conditions.append(Conversation.channel_account_id == channel_account_id)
        if status is not None:
            conditions.append(Conversation.status == status)
        if assignee_user_id is not None:
            conditions.append(Conversation.assignee_user_id == assignee_user_id)
        if unassigned:
            conditions.append(Conversation.assignee_type == AssigneeType.unassigned.value)

        q = select(Conversation).where(Conversation.deleted_at.is_(None))
        for cond in conditions:
            q = q.where(cond)
        q = apply_filters(q, Conversation, query_request.filters, self.ALLOWED_FIELDS)
        q = apply_sorting(q, Conversation, query_request.sorting, self.ALLOWED_FIELDS)
        q = apply_pagination(q, query_request.pagination)
        items = list((await db.execute(q)).scalars().all())

        count_q = build_count_query(Conversation, query_request.filters, self.ALLOWED_FIELDS).where(
            Conversation.deleted_at.is_(None)
        )
        for cond in conditions:
            count_q = count_q.where(cond)
        total = (await db.execute(count_q)).scalar() or 0
        return items, total


conversation_repository = ConversationRepository()
