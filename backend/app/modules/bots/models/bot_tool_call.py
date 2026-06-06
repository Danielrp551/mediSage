"""
BotToolCall = traza INMUTABLE de una invocación de tool dentro de un turno (args + result +
status + latencia). SIN SoftDeleteMixin. tool_use_id = el id del tool_use del LLM (para matchear
cuando el modelo pide varias tools en una vuelta). bot_event_id (nullable) la ata al turno
(BotEvent). FK reales a conversation/bot_event/bot_tool.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class BotToolCall(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "bot_tool_call"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    bot_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bot_event.id"), nullable=True, index=True
    )
    bot_tool_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_tool.id"), nullable=False, index=True
    )
    tool_use_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ToolCallStatus
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
