"""
BotConfiguration CRUD endpoints + versiones + activate-version (molde
`conversations.channel_account`). Permiso vía `dependencies=[Depends(RequirePermission("..."))]`
en el decorator; `actor: CurrentAuth` aparte cuando el handler necesita el id para audit.
`/active` declarado ANTES de `/{id}` (sino /{id} capturaría "active"). El aggregator ya pone
`/bots`; este sub-router añade `/configurations`.

F1: CRUD config + versiones + activate-version. Los endpoints M:N `/{id}/tools` llegan en F2.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.bots.schemas.bot_configuration import (
    BotConfigurationCreate,
    BotConfigurationDetail,
    BotConfigurationItem,
    BotConfigurationOption,
    BotConfigurationUpdate,
)
from app.modules.bots.schemas.bot_configuration_version import (
    BotConfigurationVersionCreate,
    BotConfigurationVersionDetail,
    BotConfigurationVersionItem,
)
from app.modules.bots.services import bot_configuration as config_service
from app.modules.bots.services import bot_configuration_version as version_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/configurations", tags=["bots · configurations"])

ConfigIdPath = Annotated[str, Path(min_length=1, description="BotConfiguration UUID")]
VersionIdPath = Annotated[str, Path(min_length=1, description="BotConfigurationVersion UUID")]


@router.get(
    "/active",
    response_model=list[BotConfigurationOption],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATIONS_READ"))],
)
async def list_active_configurations(db: DBSession) -> list[BotConfigurationOption]:
    return await config_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[BotConfigurationItem],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATIONS_READ"))],
)
async def list_configurations(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[BotConfigurationItem]:
    return await config_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[BotConfigurationDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATIONS_CREATE"))],
)
async def create_configuration(
    payload: BotConfigurationCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[BotConfigurationDetail]:
    return await config_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{configuration_id}",
    response_model=SingleResponse[BotConfigurationDetail],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATIONS_READ"))],
)
async def get_configuration(
    configuration_id: ConfigIdPath, db: DBSession
) -> SingleResponse[BotConfigurationDetail]:
    return await config_service.get_by_id(db, configuration_id)


@router.put(
    "/{configuration_id}",
    response_model=SingleResponse[BotConfigurationDetail],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATIONS_UPDATE"))],
)
async def update_configuration(
    configuration_id: ConfigIdPath,
    payload: BotConfigurationUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[BotConfigurationDetail]:
    return await config_service.update(db, configuration_id, payload, actor_id=actor.id)


@router.delete(
    "/{configuration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATIONS_DELETE"))],
)
async def delete_configuration(
    configuration_id: ConfigIdPath, db: DBSession, actor: CurrentAuth
) -> None:
    await config_service.soft_delete(db, configuration_id, actor_id=actor.id)


# ── Versiones ───────────────────────────────────────────────────────


@router.get(
    "/{configuration_id}/versions",
    response_model=SingleResponse[list[BotConfigurationVersionItem]],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATION_VERSIONS_READ"))],
)
async def list_versions(
    configuration_id: ConfigIdPath, db: DBSession
) -> SingleResponse[list[BotConfigurationVersionItem]]:
    return await version_service.list_for_config(db, configuration_id)


@router.post(
    "/{configuration_id}/versions",
    response_model=SingleResponse[BotConfigurationVersionDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATION_VERSIONS_WRITE"))],
)
async def create_version(
    configuration_id: ConfigIdPath,
    payload: BotConfigurationVersionCreate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[BotConfigurationVersionDetail]:
    return await version_service.create(db, configuration_id, payload, actor_id=actor.id)


@router.get(
    "/{configuration_id}/versions/{version_id}",
    response_model=SingleResponse[BotConfigurationVersionDetail],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATION_VERSIONS_READ"))],
)
async def get_version(
    configuration_id: ConfigIdPath, version_id: VersionIdPath, db: DBSession
) -> SingleResponse[BotConfigurationVersionDetail]:
    return await version_service.get_one(db, configuration_id, version_id)


@router.post(
    "/{configuration_id}/activate-version/{version_id}",
    response_model=SingleResponse[BotConfigurationDetail],
    dependencies=[Depends(RequirePermission("BOT_CONFIGURATION_VERSIONS_WRITE"))],
)
async def activate_version(
    configuration_id: ConfigIdPath,
    version_id: VersionIdPath,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[BotConfigurationDetail]:
    return await config_service.activate_version(
        db, configuration_id, version_id, actor_id=actor.id
    )
