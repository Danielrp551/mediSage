"""
BotTool service. Módulo de funciones (molde `catalog.vertical`/`crm.lead_status`): CRUD del
catálogo de tools (guard unicidad → 409 BOT_TOOL_CODE_TAKEN) + el set bulk del M:N
`set_config_tools` (valida que el bot exista + que TODOS los tool_ids existan → BOT_TOOL_NOT_FOUND).
`is_registered` es denormalizado: `tool.code in TOOL_REGISTRY` (el registry se puebla al importar
`engine.tools`, que registra las tools MVP crm/catalog por su `code`). Audit users por batch (sin
N+1). `code` NO se edita tras crear (es la clave que cruza con el registry).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.models.bot_tool import BotTool
from app.modules.bots.repositories.bot_configuration import bot_configuration_repository
from app.modules.bots.repositories.bot_tool import bot_tool_repository
from app.modules.bots.schemas.bot_configuration import BotConfigurationDetail
from app.modules.bots.schemas.bot_tool import (
    BotToolCreate,
    BotToolDetail,
    BotToolItem,
    BotToolOption,
    BotToolUpdate,
    ConfigurationToolsUpdate,
)
from app.modules.bots.services import bot_configuration as bot_configuration_service
from app.modules.bots.services.engine.tools import TOOL_REGISTRY
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


def _to_item(tool: BotTool, audit_users: dict[str, User]) -> BotToolItem:
    return BotToolItem(
        id=tool.id,
        code=tool.code,
        name=tool.name,
        description=tool.description,
        target_service=tool.target_service,
        requires_confirmation=tool.requires_confirmation,
        is_registered=tool.code in TOOL_REGISTRY,
        active=tool.active,
        created_on=tool.created_on,
        created_by=tool.created_by,
        created_by_user=_audit_info(audit_users.get(tool.created_by)),
        updated_on=tool.updated_on,
        updated_by=tool.updated_by,
        updated_by_user=_audit_info(audit_users.get(tool.updated_by)),
    )


def _to_detail(tool: BotTool, audit_users: dict[str, User]) -> BotToolDetail:
    return BotToolDetail(
        **_to_item(tool, audit_users).model_dump(),
        parameters_schema=tool.parameters_schema,
    )


async def _detail_response(db: AsyncSession, tool: BotTool) -> SingleResponse[BotToolDetail]:
    audit_users = await user_repository.get_audit_info_map(db, {tool.created_by, tool.updated_by})
    return SingleResponse(data=_to_detail(tool, audit_users))


async def list_active(db: AsyncSession) -> list[BotToolOption]:
    rows = await bot_tool_repository.list_active(db)
    return [BotToolOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, tool_id: str) -> SingleResponse[BotToolDetail]:
    tool = await bot_tool_repository.get_by_id(db, tool_id)
    if tool is None:
        raise NotFoundException("Tool no encontrada", code="BOT_TOOL_NOT_FOUND")
    return await _detail_response(db, tool)


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[BotToolItem]:
    items, total = await bot_tool_repository.get_paginated(db, query_request)
    actor_ids: set[str] = set()
    for t in items:
        actor_ids.add(t.created_by)
        actor_ids.add(t.updated_by)
    audit_users = await user_repository.get_audit_info_map(db, actor_ids)
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(t, audit_users) for t in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: BotToolCreate, *, actor_id: str
) -> SingleResponse[BotToolDetail]:
    existing = await bot_tool_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe una tool con el código '{payload.code}'",
            code="BOT_TOOL_CODE_TAKEN",
        )
    now = utc_now()
    tool = BotTool(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        parameters_schema=payload.parameters_schema,
        target_service=payload.target_service,
        requires_confirmation=payload.requires_confirmation,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await bot_tool_repository.create(db, tool)
    return await _detail_response(db, tool)


async def update(
    db: AsyncSession, tool_id: str, payload: BotToolUpdate, *, actor_id: str
) -> SingleResponse[BotToolDetail]:
    tool = await bot_tool_repository.get_by_id(db, tool_id)
    if tool is None:
        raise NotFoundException("Tool no encontrada", code="BOT_TOOL_NOT_FOUND")
    # Todos los campos del Update mapean a columnas NOT NULL → None = "no cambiar" (no blanquear).
    # `code` NO está en el Update (inmutable). `requires_confirmation`/`active` False sí cambian.
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await bot_tool_repository.update(db, tool, changes)
    return await _detail_response(db, tool)


async def soft_delete(db: AsyncSession, tool_id: str, *, actor_id: str) -> None:
    tool = await bot_tool_repository.get_by_id(db, tool_id)
    if tool is None:
        raise NotFoundException("Tool no encontrada", code="BOT_TOOL_NOT_FOUND")
    tool.updated_by = actor_id
    tool.updated_on = utc_now()
    await bot_tool_repository.soft_delete(db, tool)


async def list_for_config(
    db: AsyncSession, bot_configuration_id: str
) -> SingleResponse[list[BotToolOption]]:
    """Tools (vivas) asignadas a un bot (para hidratar el multiselect del editor M:N)."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    tool_ids = await bot_tool_repository.tool_ids_for_config(db, bot_configuration_id)
    tools = await bot_tool_repository.get_by_ids(db, tool_ids)
    tools.sort(key=lambda t: t.name)
    options = [BotToolOption.model_validate(t, from_attributes=True) for t in tools]
    return SingleResponse(data=options)


async def set_config_tools(
    db: AsyncSession,
    bot_configuration_id: str,
    payload: ConfigurationToolsUpdate,
    *,
    actor_id: str,
) -> SingleResponse[BotConfigurationDetail]:
    """Reemplaza el conjunto de tools del bot. Valida que el bot exista + que TODOS los tool_ids
    existan (BOT_TOOL_NOT_FOUND si alguno no, vivo). Molde del editor de matriz de crm."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    requested = list(dict.fromkeys(payload.tool_ids))  # dedup preservando orden
    found = await bot_tool_repository.get_by_ids(db, requested)
    found_ids = {t.id for t in found}
    missing = [tid for tid in requested if tid not in found_ids]
    if missing:
        raise NotFoundException(f"Tool no encontrada: {missing[0]}", code="BOT_TOOL_NOT_FOUND")
    await bot_tool_repository.set_config_tools(db, bot_configuration_id, requested)
    config.updated_by = actor_id
    config.updated_on = utc_now()
    await db.flush()
    return await bot_configuration_service.get_by_id(db, bot_configuration_id)
