"""
ConversationBotState service (panel de depuración). `get_state` (404 BOT_STATE_NOT_FOUND si el hilo
no tiene estado de bot) + `reset_state` (limpia slots/intent/last_node/turn_count y re-fija la
versión vigente del bot — para que el hilo salte a la última versión tras un activate-version; NO
toca el assignee del hilo). Denormaliza bot_configuration_code + version_number (lookups directos).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.bots.models.conversation_bot_state import ConversationBotState
from app.modules.bots.repositories.bot_configuration import bot_configuration_repository
from app.modules.bots.repositories.bot_configuration_version import (
    bot_configuration_version_repository,
)
from app.modules.bots.repositories.conversation_bot_state import (
    conversation_bot_state_repository,
)
from app.modules.bots.schemas.conversation_bot_state import (
    ConversationBotStateDetail,
    ResetBotStateRequest,
)
from app.shared.base_schemas import SingleResponse
from app.shared.utils import utc_now


async def _to_detail(db: AsyncSession, state: ConversationBotState) -> ConversationBotStateDetail:
    config = await bot_configuration_repository.get_by_id(db, state.bot_configuration_id)
    version = await bot_configuration_version_repository.get_by_id(
        db, state.bot_configuration_version_id
    )
    return ConversationBotStateDetail(
        id=state.id,
        conversation_id=state.conversation_id,
        bot_configuration_id=state.bot_configuration_id,
        bot_configuration_version_id=state.bot_configuration_version_id,
        bot_configuration_code=config.code if config is not None else None,
        version_number=version.version if version is not None else None,
        current_intent=state.current_intent,
        collected_slots=state.collected_slots,
        last_node=state.last_node,
        last_bot_turn_at=state.last_bot_turn_at,
        turn_count=state.turn_count,
        active=state.active,
        created_on=state.created_on,
        updated_on=state.updated_on,
    )


async def get_state(
    db: AsyncSession, conversation_id: str
) -> SingleResponse[ConversationBotStateDetail]:
    state = await conversation_bot_state_repository.get_by_conversation(db, conversation_id)
    if state is None:
        raise NotFoundException(
            "El bot no tiene estado en esta conversación", code="BOT_STATE_NOT_FOUND"
        )
    return SingleResponse(data=await _to_detail(db, state))


async def reset_state(
    db: AsyncSession,
    conversation_id: str,
    payload: ResetBotStateRequest,
    *,
    actor_id: str,
) -> SingleResponse[ConversationBotStateDetail]:
    """Limpia el estado del bot y re-fija la versión vigente. NO toca el assignee (eso es de
    conversations). 404 si el hilo no tiene estado de bot."""
    state = await conversation_bot_state_repository.get_by_conversation(db, conversation_id)
    if state is None:
        raise NotFoundException(
            "El bot no tiene estado en esta conversación", code="BOT_STATE_NOT_FOUND"
        )
    config = await bot_configuration_repository.get_by_id(db, state.bot_configuration_id)
    state.collected_slots = {}
    state.current_intent = None
    state.last_node = None
    state.turn_count = 0
    if config is not None and config.current_version_id is not None:
        state.bot_configuration_version_id = config.current_version_id  # salta a la vigente
    state.updated_by = actor_id
    state.updated_on = utc_now()
    await db.flush()
    return SingleResponse(data=await _to_detail(db, state))
