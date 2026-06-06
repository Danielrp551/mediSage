"""
ConversationBotState repository. Se consulta por conversation_id (UNIQUE) para el panel de
depuración y para el load-or-create del motor. NO se pagina/filtra desde el front
(ALLOWED_FIELDS vacío).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.conversation_bot_state import ConversationBotState
from app.shared.base_repository import BaseRepository


class ConversationBotStateRepository(BaseRepository[ConversationBotState]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(ConversationBotState)

    async def get_by_conversation(
        self, db: AsyncSession, conversation_id: str
    ) -> ConversationBotState | None:
        result = await db.execute(
            select(ConversationBotState).where(
                ConversationBotState.conversation_id == conversation_id,
                ConversationBotState.deleted_at.is_(None),
            )
        )
        return result.scalars().first()


conversation_bot_state_repository = ConversationBotStateRepository()
