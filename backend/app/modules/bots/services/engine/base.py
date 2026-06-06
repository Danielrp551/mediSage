"""
Interfaz del motor de bots (ADR-005). El motor es agnóstico al provider del LLM; las
implementaciones concretas (EmbeddedBotEngine en el MVP; ExternalBotEngine DIFERIDO) corren un
turno completo de una conversación. `choose_bot_for_conversation` resuelve el bot efectivo del hilo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_configuration import BotConfiguration
from app.modules.bots.repositories.bot_configuration import bot_configuration_repository
from app.modules.conversations.models.conversation import Conversation


class BotEngine(ABC):
    @abstractmethod
    async def dispatch_turn(
        self, db: AsyncSession, *, conversation_id: str, input_message_id: str | None
    ) -> None:
        """Corre UN turno del bot sobre la conversación. Lee el historial del hilo (Firestore),
        llama al LLM, ejecuta tools, responde (send_bot_outbound) y persiste las trazas. NO lanza
        5xx salvo para forzar el reintento de Cloud Tasks (los errores de provider se capturan →
        BotEvent(turn_failed) + mensaje de fallback)."""
        ...


async def choose_bot_for_conversation(
    db: AsyncSession, conversation: Conversation
) -> BotConfiguration | None:
    """MVP: el bot efectivo es el de la conversación (conversation.bot_configuration_id, que setea
    el handoff release→bot o el hook de find_or_create_open en F3b). None si el hilo no tiene bot."""
    if conversation.bot_configuration_id is None:
        return None
    return await bot_configuration_repository.get_by_id(db, conversation.bot_configuration_id)
