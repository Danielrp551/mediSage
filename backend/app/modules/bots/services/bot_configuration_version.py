"""
BotConfigurationVersion service. Módulo de funciones (no clases). Las versiones son INMUTABLES:
se crean (version = max+1) pero no se editan in-place ni se borran. La promoción a vigente vive en
`bot_configuration.activate_version`. `to_item`/`to_detail` son reutilizables (los usa
`bot_configuration` para expandir la versión vigente en el Detail). `is_active` = `ActiveMixin.active`;
`is_current` = (version.id == config.current_version_id) — ambos denormalizados acá.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.enums import BotProvider
from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion
from app.modules.bots.repositories.bot_configuration import bot_configuration_repository
from app.modules.bots.repositories.bot_configuration_version import (
    bot_configuration_version_repository,
)
from app.modules.bots.schemas.bot_configuration_version import (
    BotConfigurationVersionCreate,
    BotConfigurationVersionDetail,
    BotConfigurationVersionItem,
)
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def to_item(
    version: BotConfigurationVersion,
    current_version_id: str | None,
    audit_users: dict[str, User],
) -> BotConfigurationVersionItem:
    return BotConfigurationVersionItem(
        id=version.id,
        bot_configuration_id=version.bot_configuration_id,
        version=version.version,
        provider=BotProvider(version.provider),
        model_name=version.model_name,
        is_active=version.active,
        is_current=version.id == current_version_id,
        notes=version.notes,
        created_on=version.created_on,
        created_by=version.created_by,
        created_by_user=_audit_info(audit_users.get(version.created_by)),
    )


def to_detail(
    version: BotConfigurationVersion,
    current_version_id: str | None,
    audit_users: dict[str, User],
) -> BotConfigurationVersionDetail:
    return BotConfigurationVersionDetail(
        **to_item(version, current_version_id, audit_users).model_dump(),
        system_prompt=version.system_prompt,
        parameters=version.parameters,
        external_webhook_url=version.external_webhook_url,
        external_webhook_secret_name=version.external_webhook_secret_name,
    )


async def get_detail(
    db: AsyncSession, version_id: str
) -> SingleResponse[BotConfigurationVersionDetail]:
    version = await bot_configuration_version_repository.get_by_id(db, version_id)
    if version is None:
        raise NotFoundException("Versión no encontrada", code="BOT_VERSION_NOT_FOUND")
    config = await bot_configuration_repository.get_by_id(db, version.bot_configuration_id)
    current_version_id = config.current_version_id if config is not None else None
    audit_users = await user_repository.get_audit_info_map(db, {version.created_by})
    return SingleResponse(data=to_detail(version, current_version_id, audit_users))


async def get_one(
    db: AsyncSession, bot_configuration_id: str, version_id: str
) -> SingleResponse[BotConfigurationVersionDetail]:
    """GET /configurations/{id}/versions/{vid}: la versión debe existir Y pertenecer al bot."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    version = await bot_configuration_version_repository.get_by_id(db, version_id)
    if version is None or version.bot_configuration_id != bot_configuration_id:
        raise NotFoundException("Versión no encontrada", code="BOT_VERSION_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(db, {version.created_by})
    return SingleResponse(data=to_detail(version, config.current_version_id, audit_users))


async def list_for_config(
    db: AsyncSession, bot_configuration_id: str
) -> SingleResponse[list[BotConfigurationVersionItem]]:
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    versions = await bot_configuration_version_repository.list_for_config(db, bot_configuration_id)
    audit_users = await user_repository.get_audit_info_map(db, {v.created_by for v in versions})
    items = [to_item(v, config.current_version_id, audit_users) for v in versions]
    return SingleResponse(data=items)


async def create(
    db: AsyncSession,
    bot_configuration_id: str,
    payload: BotConfigurationVersionCreate,
    *,
    actor_id: str,
) -> SingleResponse[BotConfigurationVersionDetail]:
    """Crea una NUEVA versión (no edita in-place). Asigna version = max+1. Valida external_webhook.
    Si el bot aún no tiene versión vigente, ESTA queda como current (primera versión = usable sin
    un activate-version extra)."""
    config = await bot_configuration_repository.get_by_id(db, bot_configuration_id)
    if config is None:
        raise NotFoundException("Bot no encontrado", code="BOT_CONFIGURATION_NOT_FOUND")
    if payload.provider == BotProvider.external_webhook and not payload.external_webhook_url:
        raise BadRequestException(
            "Se requiere la URL del webhook externo para el proveedor external_webhook",
            code="EXTERNAL_WEBHOOK_URL_REQUIRED",
        )
    next_version = (
        await bot_configuration_version_repository.max_version(db, bot_configuration_id) + 1
    )
    now = utc_now()
    version = BotConfigurationVersion(
        id=generate_uuid(),
        bot_configuration_id=bot_configuration_id,
        version=next_version,
        system_prompt=payload.system_prompt,
        provider=payload.provider.value,
        model_name=payload.model_name,
        parameters=payload.parameters,
        external_webhook_url=payload.external_webhook_url,
        external_webhook_secret_name=payload.external_webhook_secret_name,
        notes=payload.notes,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(version)
    await db.flush()
    if config.current_version_id is None:
        config.current_version_id = version.id
        config.updated_by = actor_id
        config.updated_on = now
    await db.flush()
    return await get_detail(db, version.id)
