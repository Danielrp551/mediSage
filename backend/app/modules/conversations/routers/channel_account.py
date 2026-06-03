"""
ChannelAccount CRUD endpoints (molde `catalog.vertical`). Permiso vía
`dependencies=[Depends(RequirePermission("..."))]` en el decorator; `actor:
CurrentAuth` aparte cuando el handler necesita el id para audit. `/active`
declarado ANTES de `/{id}` (sino /{id} capturaría "active").

`/list` es POST + body (`QueryRequest`) porque el payload de filtros puede ser
arbitrariamente grande. El aggregator ya pone `/conversations`; este sub-router
añade `/channel-accounts`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.conversations.schemas.channel_account import (
    ChannelAccountCreate,
    ChannelAccountDetail,
    ChannelAccountItem,
    ChannelAccountOption,
    ChannelAccountUpdate,
)
from app.modules.conversations.services import channel_account as channel_account_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/channel-accounts", tags=["conversations · channel-accounts"])


ChannelAccountIdPath = Annotated[str, Path(min_length=1, description="ChannelAccount UUID")]


@router.get(
    "/active",
    response_model=list[ChannelAccountOption],
    dependencies=[Depends(RequirePermission("CHANNEL_ACCOUNTS_READ"))],
)
async def list_active_channel_accounts(db: DBSession) -> list[ChannelAccountOption]:
    return await channel_account_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[ChannelAccountItem],
    dependencies=[Depends(RequirePermission("CHANNEL_ACCOUNTS_READ"))],
)
async def list_channel_accounts(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[ChannelAccountItem]:
    return await channel_account_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[ChannelAccountDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("CHANNEL_ACCOUNTS_CREATE"))],
)
async def create_channel_account(
    payload: ChannelAccountCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ChannelAccountDetail]:
    return await channel_account_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{channel_account_id}",
    response_model=SingleResponse[ChannelAccountDetail],
    dependencies=[Depends(RequirePermission("CHANNEL_ACCOUNTS_READ"))],
)
async def get_channel_account(
    channel_account_id: ChannelAccountIdPath, db: DBSession
) -> SingleResponse[ChannelAccountDetail]:
    return await channel_account_service.get_by_id(db, channel_account_id)


@router.put(
    "/{channel_account_id}",
    response_model=SingleResponse[ChannelAccountDetail],
    dependencies=[Depends(RequirePermission("CHANNEL_ACCOUNTS_UPDATE"))],
)
async def update_channel_account(
    channel_account_id: ChannelAccountIdPath,
    payload: ChannelAccountUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ChannelAccountDetail]:
    return await channel_account_service.update(db, channel_account_id, payload, actor_id=actor.id)


@router.delete(
    "/{channel_account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("CHANNEL_ACCOUNTS_DELETE"))],
)
async def delete_channel_account(
    channel_account_id: ChannelAccountIdPath, db: DBSession, actor: CurrentAuth
) -> None:
    await channel_account_service.soft_delete(db, channel_account_id, actor_id=actor.id)
