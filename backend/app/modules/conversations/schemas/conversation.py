"""
Schemas de Conversation. `ConversationListItem` (row del inbox) + `ConversationDetail`
(detalle + historial de handoff) + `ConversationAssignmentLogItem` + los request bodies
de handoff (`Take`/`Release`, consumidos en F3).

`person` se denormaliza reusando `crm.schemas.person.PersonOption` (id/full_name/
document_number/primary_identifier) — conversations NO redefine el shape de la persona;
lo puebla vía un batch map de crm (ver el service). `channel_account` reusa
`ChannelAccountOption`; `assignee_user` reusa `UserAuditInfo` de admin. `last_message_*`
+ `unread_count` son columnas reales de `conversation`. Convenciones: from_attributes en
los Item/Detail; validators en inglés (422); copy en español en el Zod del front.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.enums import AssigneeType, ConversationStatus
from app.modules.conversations.schemas.channel_account import ChannelAccountOption
from app.modules.crm.schemas.person import PersonOption  # denormalizado vía batch map de crm


class ConversationListItem(BaseModel):
    """Row del inbox (lista 2-paneles). person/channel/assignee denormalizados (sin N+1);
    last_message_* + unread_count son columnas reales de conversation."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    channel_account: ChannelAccountOption
    person: PersonOption | None = None
    status: ConversationStatus
    assignee_type: AssigneeType
    assignee_user: UserAuditInfo | None = None
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    unread_count: int
    created_on: datetime


class ConversationAssignmentLogItem(BaseModel):
    """Una fila del historial de handoff (audit inmutable)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    from_assignee_type: AssigneeType | None = None
    from_assignee_user: UserAuditInfo | None = None
    to_assignee_type: AssigneeType
    to_assignee_user: UserAuditInfo | None = None
    started_at: datetime
    ended_at: datetime | None = None
    by_actor_user: UserAuditInfo | None = None
    reason: str | None = None


class ConversationDetail(ConversationListItem):
    """Extiende ListItem con la config del hilo + el historial de handoff."""

    bot_configuration_id: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    assignment_history: list[ConversationAssignmentLogItem] = Field(default_factory=list)


class TakeConversationRequest(BaseModel):
    """Body de POST /conversations/{id}/take (F3)."""

    reason: str | None = Field(default=None, max_length=255)


class ReleaseConversationRequest(BaseModel):
    """Body de POST /conversations/{id}/release (F3). to_assignee_type ∈ {bot, unassigned}
    en el MVP (advisor = take). to_bot_configuration_id solo si bots existiera (hoy NULL)."""

    to_assignee_type: AssigneeType
    to_bot_configuration_id: str | None = Field(default=None, max_length=36)
    reason: str | None = Field(default=None, max_length=255)
