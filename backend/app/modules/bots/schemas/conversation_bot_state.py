"""
Schemas del estado del bot por conversación (panel de depuración, read-only salvo el reset).
`bot_configuration_code`/`version_number` son denormalizados (batch lookup en el service).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationBotStateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    bot_configuration_id: str
    bot_configuration_version_id: str
    bot_configuration_code: str | None = None  # denormalizado (depuración)
    version_number: int | None = None  # denormalizado
    current_intent: str | None
    collected_slots: dict[str, Any] = Field(default_factory=dict)
    last_node: str | None
    last_bot_turn_at: datetime | None
    turn_count: int
    active: bool
    created_on: datetime
    updated_on: datetime


class ConversationBotStateDetail(ConversationBotStateItem):
    """Para el panel de depuración: igual que Item por ahora (la timeline de eventos y las tool
    calls se traen por sus propios endpoints)."""

    pass


class ResetBotStateRequest(BaseModel):
    """Body de POST /conversations/{cid}/state/reset. Limpia slots/intent/turn_count y re-fija la
    versión vigente del bot. `reason` opcional (auditoría)."""

    reason: str | None = Field(default=None, max_length=255)
