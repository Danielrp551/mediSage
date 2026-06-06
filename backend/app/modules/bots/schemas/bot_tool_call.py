"""
Schema de BotToolCall (traza por invocación de tool, read-only depuración). `bot_tool_code` es
denormalizado (batch lookup en el service, para mostrar sin join extra).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.bots.enums import ToolCallStatus


class BotToolCallItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    bot_event_id: str | None
    bot_tool_id: str
    bot_tool_code: str | None = None  # denormalizado (depuración)
    tool_use_id: str | None
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    status: ToolCallStatus
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    latency_ms: int | None
    created_on: datetime
