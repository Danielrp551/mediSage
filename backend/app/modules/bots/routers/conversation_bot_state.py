"""
Endpoints de depuración del bot por conversación (state + reset + events + tool-calls). Read-only
salvo `state/reset`. Permiso vía `dependencies=[Depends(RequirePermission("..."))]`. El aggregator
pone `/bots`; este sub-router añade `/conversations` → `/api/v1/bots/conversations/{cid}/...`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.bots.schemas.bot_event import BotEventItem
from app.modules.bots.schemas.bot_tool_call import BotToolCallItem
from app.modules.bots.schemas.conversation_bot_state import (
    ConversationBotStateDetail,
    ResetBotStateRequest,
)
from app.modules.bots.services import bot_event as event_service
from app.modules.bots.services import bot_tool_call as tool_call_service
from app.modules.bots.services import conversation_bot_state as state_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/conversations", tags=["bots · trace"])

CidPath = Annotated[str, Path(min_length=1, description="Conversation UUID")]


@router.get(
    "/{conversation_id}/state",
    response_model=SingleResponse[ConversationBotStateDetail],
    dependencies=[Depends(RequirePermission("BOT_STATE_READ"))],
)
async def get_state(
    conversation_id: CidPath, db: DBSession
) -> SingleResponse[ConversationBotStateDetail]:
    return await state_service.get_state(db, conversation_id)


@router.post(
    "/{conversation_id}/state/reset",
    response_model=SingleResponse[ConversationBotStateDetail],
    dependencies=[Depends(RequirePermission("BOT_STATE_WRITE"))],
)
async def reset_state(
    conversation_id: CidPath,
    payload: ResetBotStateRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ConversationBotStateDetail]:
    return await state_service.reset_state(db, conversation_id, payload, actor_id=actor.id)


@router.get(
    "/{conversation_id}/events",
    response_model=SingleResponse[list[BotEventItem]],
    dependencies=[Depends(RequirePermission("BOT_EVENTS_READ"))],
)
async def list_events(
    conversation_id: CidPath, db: DBSession
) -> SingleResponse[list[BotEventItem]]:
    return await event_service.list_events(db, conversation_id)


@router.get(
    "/{conversation_id}/tool-calls",
    response_model=SingleResponse[list[BotToolCallItem]],
    dependencies=[Depends(RequirePermission("BOT_TOOL_CALLS_READ"))],
)
async def list_tool_calls(
    conversation_id: CidPath, db: DBSession
) -> SingleResponse[list[BotToolCallItem]]:
    return await tool_call_service.list_tool_calls(db, conversation_id)
