"""
ConversationBotState = el estado de la sesión del bot en UNA conversación (slots recolectados,
intent actual, contador de turnos, versión con la que arrancó). UNIQUE conversation_id (un solo
estado por hilo). bot_configuration_version_id congela la versión con la que el hilo viene operando
(NO se migra al promover otra versión; reset explícito vía /state/reset). FK real a conversation
(existe) + bot_configuration + bot_configuration_version.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class ConversationBotState(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "conversation_bot_state"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, unique=True, index=True
    )
    bot_configuration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration.id"), nullable=False, index=True
    )
    bot_configuration_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration_version.id"), nullable=False, index=True
    )
    current_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    collected_slots: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    last_node: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_bot_turn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
