"""
ConversationAssignmentLog = historial INMUTABLE de handoff de una Conversation (quién
la tuvo, cuándo, quién hizo el cambio). SIN SoftDeleteMixin (audit trail). A lo sumo
UNA fila vigente (`ended_at IS NULL`) por conversación — lo garantiza el SERVICE
(close_current antes de open_new, misma tx; NO un UNIQUE parcial). `from_*` es NULL en
el primer log (auto-asignación / alta). Las FKs a user son reales; `by_actor_user_id`
NULL = cambio automático (sistema / auto-asignación al crear el hilo).

F2 escribe la PRIMERA fila (auto-asignación en find_or_create_open). Las transiciones
de handoff (take/release/close/reopen) que abren/cierran filas llegan en F3.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class ConversationAssignmentLog(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "conversation_assignment_log"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    from_assignee_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # NULL primer log
    from_assignee_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    to_assignee_type: Mapped[str] = mapped_column(String(20), nullable=False)  # AssigneeType
    to_assignee_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # NULL = vigente
    # FK real → user.id. NULL = cambio automático (sistema / auto-asignación).
    by_actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
