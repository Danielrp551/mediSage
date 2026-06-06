"""
BotEvent service (read-only, timeline de depuración). Mapea cada traza a BotEventItem; el atributo
del modelo es `event_metadata` (la columna se llama "metadata") → se expone como `metadata`. NO
404ea si el hilo no tiene eventos: devuelve lista vacía (semántica de timeline).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_event import BotEvent
from app.modules.bots.repositories.bot_event import bot_event_repository
from app.modules.bots.schemas.bot_event import BotEventItem
from app.shared.base_schemas import SingleResponse


def _to_item(event: BotEvent) -> BotEventItem:
    return BotEventItem(
        id=event.id,
        conversation_id=event.conversation_id,
        bot_configuration_id=event.bot_configuration_id,
        bot_configuration_version_id=event.bot_configuration_version_id,
        turn_number=event.turn_number,
        event_type=event.event_type,
        input_message_id=event.input_message_id,
        output_message_id=event.output_message_id,
        tokens_in=event.tokens_in,
        tokens_out=event.tokens_out,
        latency_ms=event.latency_ms,
        cost_estimated_usd=event.cost_estimated_usd,
        error=event.error,
        metadata=event.event_metadata,
        created_on=event.created_on,
    )


async def list_events(db: AsyncSession, conversation_id: str) -> SingleResponse[list[BotEventItem]]:
    events = await bot_event_repository.list_for_conversation(db, conversation_id)
    return SingleResponse(data=[_to_item(e) for e in events])
