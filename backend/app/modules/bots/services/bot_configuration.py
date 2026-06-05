"""
BotConfiguration service. Módulo de funciones (no clases), molde `catalog.vertical`/
`conversations.channel_account`: `list_paginated`, `create` (guard unicidad → 409
BOT_CONFIGURATION_CODE_TAKEN), `get_by_id`, `update`, `soft_delete`, `list_active`. Lo específico
de bots: `activate_version` (promueve una versión a vigente) y los denormalizados de lectura
(`current_version_number`/`version_count` por batch lookup, sin N+1) + la versión vigente expandida
en el Detail. `tool_ids` (M:N) llega en F2 → en F1 SIEMPRE []. Audit users hidratados por batch.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyExistsException,
    BadRequestException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.models.bot_configuration import BotConfiguration
from app.modules.bots.repositories.bot_configuration import bot_configuration_repository
from app.modules.bots.repositories.bot_configuration_version import (
    bot_configuration_version_repository,
)
from app.modules.bots.repositories.bot_tool import bot_tool_repository
from app.modules.bots.schemas.bot_configuration import (
    BotConfigurationCreate,
    BotConfigurationDetail,
    BotConfigurationItem,
    BotConfigurationOption,
    BotConfigurationUpdate,
)
from app.modules.bots.services import bot_configuration_version as version_service
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(
    config: BotConfiguration,
    version_count_map: dict[str, int],
    current_number_map: dict[str, int],
    audit_users: dict[str, User],
) -> BotConfigurationItem:
    current_number = (
        current_number_map.get(config.current_version_id)
        if config.current_version_id is not None
        else None
    )
    return BotConfigurationItem(
        id=config.id,
        code=config.code,
        name=config.name,
        bot_type=config.bot_type,
        description=config.description,
        current_version_id=config.current_version_id,
        current_version_number=current_number,
        max_turns_per_conversation=config.max_turns_per_conversation,
        version_count=version_count_map.get(config.id, 0),
        active=config.active,
        created_on=config.created_on,
        created_by=config.created_by,
        created_by_user=_audit_info(audit_users.get(config.created_by)),
        updated_on=config.updated_on,
        updated_by=config.updated_by,
        updated_by_user=_audit_info(audit_users.get(config.updated_by)),
    )


async def _build_detail(db: AsyncSession, config: BotConfiguration) -> BotConfigurationDetail:
    """Detail = Item + versión vigente expandida (si la hay) + tool_ids del M:N (F2)."""
    version_count = (
        await bot_configuration_version_repository.version_count_map(db, [config.id])
    ).get(config.id, 0)
    tool_ids = await bot_tool_repository.tool_ids_for_config(db, config.id)

    actor_ids = {config.created_by, config.updated_by}
    current_version = None
    if config.current_version_id is not None:
        current_version = await bot_configuration_version_repository.get_by_id(
            db, config.current_version_id
        )
        if current_version is not None:
            actor_ids.add(current_version.created_by)

    audit_users = await user_repository.get_audit_info_map(db, actor_ids)
    current_version_item = (
        version_service.to_item(current_version, config.current_version_id, audit_users)
        if current_version is not None
        else None
    )
    return BotConfigurationDetail(
        id=config.id,
        code=config.code,
        name=config.name,
        bot_type=config.bot_type,
        description=config.description,
        current_version_id=config.current_version_id,
        current_version_number=current_version.version if current_version is not None else None,
        max_turns_per_conversation=config.max_turns_per_conversation,
        version_count=version_count,
        active=config.active,
        created_on=config.created_on,
        created_by=config.created_by,
        created_by_user=_audit_info(audit_users.get(config.created_by)),
        updated_on=config.updated_on,
        updated_by=config.updated_by,
        updated_by_user=_audit_info(audit_users.get(config.updated_by)),
        current_version=current_version_item,
        tool_ids=tool_ids,
    )


async def list_active(db: AsyncSession) -> list[BotConfigurationOption]:
    rows = await bot_configuration_repository.list_active(db)
    return [BotConfigurationOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, config_id: str) -> SingleResponse[BotConfigurationDetail]:
    config = await bot_configuration_repository.get_by_id(db, config_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    return SingleResponse(data=await _build_detail(db, config))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[BotConfigurationItem]:
    items, total = await bot_configuration_repository.get_paginated(db, query_request)
    config_ids = [c.id for c in items]
    version_count_map = await bot_configuration_version_repository.version_count_map(db, config_ids)
    current_version_ids = [c.current_version_id for c in items if c.current_version_id is not None]
    current_number_map = await bot_configuration_version_repository.numbers_by_ids(
        db, current_version_ids
    )
    actor_ids: set[str] = set()
    for c in items:
        actor_ids.add(c.created_by)
        actor_ids.add(c.updated_by)
    audit_users = await user_repository.get_audit_info_map(db, actor_ids)
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(c, version_count_map, current_number_map, audit_users) for c in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: BotConfigurationCreate, *, actor_id: str
) -> SingleResponse[BotConfigurationDetail]:
    existing = await bot_configuration_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe un bot con el código '{payload.code}'",
            code="BOT_CONFIGURATION_CODE_TAKEN",
        )
    now = utc_now()
    config = BotConfiguration(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        bot_type=payload.bot_type.value,
        description=payload.description,
        current_version_id=None,
        max_turns_per_conversation=payload.max_turns_per_conversation,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await bot_configuration_repository.create(db, config)
    return SingleResponse(data=await _build_detail(db, config))


async def update(
    db: AsyncSession, config_id: str, payload: BotConfigurationUpdate, *, actor_id: str
) -> SingleResponse[BotConfigurationDetail]:
    config = await bot_configuration_repository.get_by_id(db, config_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    # null EXPLÍCITO en una columna NOT NULL del Update parcial = "no cambiar" (no blanquear).
    for required in ("code", "name", "bot_type", "active"):
        if required in changes and changes[required] is None:
            changes.pop(required)
    # `code` editable → re-dispara el guard de unicidad sobre el code vivo.
    if "code" in changes:
        clash = await bot_configuration_repository.get_by_code(db, changes["code"])
        if clash is not None and clash.id != config.id:
            raise AlreadyExistsException(
                f"Ya existe un bot con el código '{changes['code']}'",
                code="BOT_CONFIGURATION_CODE_TAKEN",
            )
    if "bot_type" in changes:
        changes["bot_type"] = changes["bot_type"].value

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await bot_configuration_repository.update(db, config, changes)
    return SingleResponse(data=await _build_detail(db, config))


async def soft_delete(db: AsyncSession, config_id: str, *, actor_id: str) -> None:
    config = await bot_configuration_repository.get_by_id(db, config_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    config.updated_by = actor_id
    config.updated_on = utc_now()
    await bot_configuration_repository.soft_delete(db, config)


async def activate_version(
    db: AsyncSession, bot_configuration_id: str, version_id: str, *, actor_id: str
) -> SingleResponse[BotConfigurationDetail]:
    """Promueve una versión a vigente (current_version_id = version_id). Valida que la versión
    EXISTA y PERTENEZCA al bot. NO migra los ConversationBotState en curso (siguen con la versión
    con la que arrancaron; reset explícito vía /state/reset — F3)."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    version = await bot_configuration_version_repository.get_by_id(db, version_id)
    if version is None:
        raise NotFoundException("Versión no encontrada", code="BOT_VERSION_NOT_FOUND")
    if version.bot_configuration_id != bot_configuration_id:
        raise BadRequestException(
            "La versión no pertenece a este bot", code="BOT_VERSION_NOT_OWNED"
        )
    config.current_version_id = version.id
    config.updated_by = actor_id
    config.updated_on = utc_now()
    await db.flush()
    return SingleResponse(data=await _build_detail(db, config))
