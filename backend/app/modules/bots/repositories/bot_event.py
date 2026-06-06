"""
BotEvent repository (traza por turno). Se lee por conversation_id (timeline de depuración, sin
paginación dinámica → ALLOWED_FIELDS vacío). `max_turn_number` lo usa el motor para asignar el
turn_number del siguiente turno.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_event import BotEvent
from app.shared.base_repository import BaseRepository


class BotEventRepository(BaseRepository[BotEvent]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(BotEvent)

    async def max_turn_number(self, db: AsyncSession, conversation_id: str) -> int:
        result = await db.execute(
            select(func.coalesce(func.max(BotEvent.turn_number), 0)).where(
                BotEvent.conversation_id == conversation_id
            )
        )
        return int(result.scalar_one())

    async def exists_for_input_message(
        self, db: AsyncSession, conversation_id: str, input_message_id: str
    ) -> bool:
        """Idempotencia del dispatch (Cloud Tasks es AT-LEAST-ONCE): ¿ya se registró un turno para
        este inbound? Cualquier BotEvent con ese `input_message_id` en la conversación basta — si un
        turno previo llegó a escribir su `turn_started`, no debemos re-ejecutar en un reintento."""
        result = await db.execute(
            select(func.count())
            .select_from(BotEvent)
            .where(
                BotEvent.conversation_id == conversation_id,
                BotEvent.input_message_id == input_message_id,
            )
        )
        return int(result.scalar_one()) > 0

    async def list_for_conversation(self, db: AsyncSession, conversation_id: str) -> list[BotEvent]:
        result = await db.execute(
            select(BotEvent)
            .where(BotEvent.conversation_id == conversation_id)
            .order_by(BotEvent.turn_number.asc(), BotEvent.created_on.asc())
        )
        return list(result.scalars().all())


bot_event_repository = BotEventRepository()
