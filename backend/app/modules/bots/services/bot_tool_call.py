"""
BotToolCall service (read-only, depuración). Denormaliza `bot_tool_code` por batch (sin N+1,
incluyendo tools soft-deleted — la traza es histórica). NO 404ea si no hay tool calls: lista vacía.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.enums import ToolCallStatus
from app.modules.bots.models.bot_tool_call import BotToolCall
from app.modules.bots.repositories.bot_tool import bot_tool_repository
from app.modules.bots.repositories.bot_tool_call import bot_tool_call_repository
from app.modules.bots.schemas.bot_tool_call import BotToolCallItem
from app.shared.base_schemas import SingleResponse


def _to_item(call: BotToolCall, code_map: dict[str, str]) -> BotToolCallItem:
    return BotToolCallItem(
        id=call.id,
        conversation_id=call.conversation_id,
        bot_event_id=call.bot_event_id,
        bot_tool_id=call.bot_tool_id,
        bot_tool_code=code_map.get(call.bot_tool_id),
        tool_use_id=call.tool_use_id,
        arguments=call.arguments,
        result=call.result,
        status=ToolCallStatus(call.status),
        error_message=call.error_message,
        started_at=call.started_at,
        completed_at=call.completed_at,
        latency_ms=call.latency_ms,
        created_on=call.created_on,
    )


async def list_tool_calls(
    db: AsyncSession, conversation_id: str
) -> SingleResponse[list[BotToolCallItem]]:
    calls = await bot_tool_call_repository.list_for_conversation(db, conversation_id)
    code_map = await bot_tool_repository.codes_by_ids(db, [c.bot_tool_id for c in calls])
    return SingleResponse(data=[_to_item(c, code_map) for c in calls])
