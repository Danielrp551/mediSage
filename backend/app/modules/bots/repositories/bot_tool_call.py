"""
BotToolCall repository (traza por invocación de tool). Se lee por conversation_id (depuración,
sin paginación dinámica → ALLOWED_FIELDS vacío).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_tool_call import BotToolCall
from app.shared.base_repository import BaseRepository


class BotToolCallRepository(BaseRepository[BotToolCall]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(BotToolCall)

    async def list_for_conversation(
        self, db: AsyncSession, conversation_id: str
    ) -> list[BotToolCall]:
        result = await db.execute(
            select(BotToolCall)
            .where(BotToolCall.conversation_id == conversation_id)
            .order_by(BotToolCall.started_at.asc())
        )
        return list(result.scalars().all())


bot_tool_call_repository = BotToolCallRepository()
