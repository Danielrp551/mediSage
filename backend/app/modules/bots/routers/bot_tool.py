"""
BotTool CRUD endpoints (catálogo de herramientas invocables). Molde `bot_configuration`. Permiso
vía `dependencies=[Depends(RequirePermission("..."))]`; `actor: CurrentAuth` aparte cuando el
handler necesita el id para audit. `/active` declarado ANTES de `/{id}` (sino /{id} capturaría
"active"). El aggregator ya pone `/bots`; este sub-router añade `/tools`.

`GET /tools/{id}` (no tabulado en la doc pero necesario): el drawer de edición trae el
`parameters_schema` (pesado), que el Item de la tabla NO expone — solo viaja en el Detail.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.bots.schemas.bot_tool import (
    BotToolCreate,
    BotToolDetail,
    BotToolItem,
    BotToolOption,
    BotToolUpdate,
)
from app.modules.bots.services import bot_tool as tool_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/tools", tags=["bots · tools"])

ToolIdPath = Annotated[str, Path(min_length=1, description="BotTool UUID")]


@router.get(
    "/active",
    response_model=list[BotToolOption],
    dependencies=[Depends(RequirePermission("BOT_TOOLS_READ"))],
)
async def list_active_tools(db: DBSession) -> list[BotToolOption]:
    return await tool_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[BotToolItem],
    dependencies=[Depends(RequirePermission("BOT_TOOLS_READ"))],
)
async def list_tools(query: QueryRequest, db: DBSession) -> PaginatedResponse[BotToolItem]:
    return await tool_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[BotToolDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("BOT_TOOLS_WRITE"))],
)
async def create_tool(
    payload: BotToolCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[BotToolDetail]:
    return await tool_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{tool_id}",
    response_model=SingleResponse[BotToolDetail],
    dependencies=[Depends(RequirePermission("BOT_TOOLS_READ"))],
)
async def get_tool(tool_id: ToolIdPath, db: DBSession) -> SingleResponse[BotToolDetail]:
    return await tool_service.get_by_id(db, tool_id)


@router.put(
    "/{tool_id}",
    response_model=SingleResponse[BotToolDetail],
    dependencies=[Depends(RequirePermission("BOT_TOOLS_WRITE"))],
)
async def update_tool(
    tool_id: ToolIdPath, payload: BotToolUpdate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[BotToolDetail]:
    return await tool_service.update(db, tool_id, payload, actor_id=actor.id)


@router.delete(
    "/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("BOT_TOOLS_WRITE"))],
)
async def delete_tool(tool_id: ToolIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await tool_service.soft_delete(db, tool_id, actor_id=actor.id)
