"""
BotEvent = traza INMUTABLE de UN turno del bot (start/complete/fail + tokens/costo/latencia).
SIN SoftDeleteMixin. INDEX (NO único) (conversation_id, turn_number): un turno tiene VARIOS eventos
(turn_started + turn_completed/turn_failed) con el MISMO turn_number. input_message_id/output_message_id
son el `mid` (doc-id Firestore: wamid inbound / uuid outbound del send_bot_outbound) en
VARCHAR(255) PLANO — NO FK (no hay tabla message; ADR-011). FK reales a conversation/
bot_configuration/bot_configuration_version. metadata = raw response/fingerprint del provider.

⚠ `metadata` es palabra reservada de SQLAlchemy Declarative (Base.metadata) → el atributo Python
se llama `event_metadata` y la columna se nombra explícitamente "metadata". El schema Pydantic
expone `metadata` (alias).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class BotEvent(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "bot_event"
    __table_args__ = (
        # NO único: un turno (turn_number) tiene VARIOS eventos (turn_started + turn_completed/
        # turn_failed) con el mismo turn_number → el índice agrupa, no restringe a 1 por turno.
        Index("ix_bot_event_conversation_turn", "conversation_id", "turn_number"),
        Index("ix_bot_event_config_created", "bot_configuration_id", "created_on"),
        Index("ix_bot_event_type_created", "event_type", "created_on"),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    bot_configuration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration.id"), nullable=False
    )
    bot_configuration_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration_version.id"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # BotEventType
    # 🔑 el `mid` (doc-id Firestore) del inbound/outbound — NO FK (no hay tabla message; ADR-011).
    input_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimated_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
