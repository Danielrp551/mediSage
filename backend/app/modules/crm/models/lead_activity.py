"""
Timeline polimórfico de una Person (ADR-003): notas, intentos de llamada,
seguimientos y eventos de sistema (cambios de estado, reasignaciones, atribución de
campaña; más adelante eventos de conversations/scheduling). SIN SoftDeleteMixin —
"borrar" = active=false (el feed normal filtra active=true). `activity_type` es el
valor de ActivityType. `payload` lleva datos por tipo. `related_appointment_id` /
`related_conversation_id` son FKs forward (ADR-009): varchar(36)+index, SIN FK
constraint ni relationship (scheduling/conversations las agregan después).

`payload` usa `JSON().with_variant(JSONB, "postgresql")`: JSONB en Postgres (prod)
y JSON en sqlite (el smoke usa create_all, no alembic; JSONB puro no serializa dicts
en sqlite). La migración escribe JSONB (solo corre en Postgres).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class LeadActivity(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "lead_activity"

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    advisor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("user.id"),
        nullable=True,  # NULL/SYSTEM en eventos de sistema
    )
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False)  # ActivityType
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ActivityOutcome
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    # FKs forward (ADR-009) — SIN FK constraint/relationship.
    related_appointment_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    related_conversation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
