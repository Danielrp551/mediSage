"""
ConversationAssignmentLog repository — el historial de handoff (audit inmutable). Se
consulta por `conversation_id` (`ALLOWED_FIELDS = set()`, no filtrable desde el front).
`list_for_conversation` alimenta `ConversationDetail.assignment_history`;
`get_current_open` (la fila vigente) lo usan las transiciones de handoff en F3.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.models.conversation_assignment_log import (
    ConversationAssignmentLog,
)
from app.shared.base_repository import BaseRepository


class ConversationAssignmentLogRepository(BaseRepository[ConversationAssignmentLog]):
    ALLOWED_FIELDS: set[str] = set()  # consultado por conversation_id

    def __init__(self) -> None:
        super().__init__(ConversationAssignmentLog)

    async def list_for_conversation(
        self, db: AsyncSession, conversation_id: str
    ) -> list[ConversationAssignmentLog]:
        """Historial completo de una conversación, más antiguo primero (para el timeline
        de handoff del detalle)."""
        result = await db.execute(
            select(ConversationAssignmentLog)
            .where(ConversationAssignmentLog.conversation_id == conversation_id)
            .order_by(ConversationAssignmentLog.started_at.asc())
        )
        return list(result.scalars().all())

    async def get_current_open(
        self, db: AsyncSession, conversation_id: str
    ) -> ConversationAssignmentLog | None:
        """La fila vigente (ended_at IS NULL) — a lo sumo una (invariante de service). La
        cierran las transiciones de handoff (F3)."""
        result = await db.execute(
            select(ConversationAssignmentLog).where(
                ConversationAssignmentLog.conversation_id == conversation_id,
                ConversationAssignmentLog.ended_at.is_(None),
            )
        )
        return result.scalars().first()

    async def close_current(
        self, db: AsyncSession, conversation_id: str, *, ended_at: datetime, actor_id: str
    ) -> None:
        """Cierra la(s) fila(s) vigente(s) (`ended_at IS NULL`) de la conversación con un
        UPDATE en bloque (sin cargar). Materializa el invariante "una sola fila vigente"
        antes de abrir la nueva (take/release) o al cerrar/reabrir el hilo (close/reopen).
        Idempotente: si no hay vigente, no afecta filas."""
        await db.execute(
            update(ConversationAssignmentLog)
            .where(
                ConversationAssignmentLog.conversation_id == conversation_id,
                ConversationAssignmentLog.ended_at.is_(None),
            )
            .values(ended_at=ended_at, updated_by=actor_id, updated_on=ended_at)
        )


conversation_assignment_log_repository = ConversationAssignmentLogRepository()
