"""
BotConfigurationVersion repository. Las versiones se leen por bot (tab de versiones); el número
lo asigna el service (max+1). `numbers_by_ids`/`version_count_map` son lookups batch para los
denormalizados de BotConfigurationItem (sin N+1).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion
from app.shared.base_repository import BaseRepository


class BotConfigurationVersionRepository(BaseRepository[BotConfigurationVersion]):
    ALLOWED_FIELDS: set[str] = {"version", "provider", "active", "created_on"}

    def __init__(self) -> None:
        super().__init__(BotConfigurationVersion)

    async def max_version(self, db: AsyncSession, bot_configuration_id: str) -> int:
        """El número de versión más alto del bot (0 si no tiene). El service asigna max+1."""
        result = await db.execute(
            select(func.coalesce(func.max(BotConfigurationVersion.version), 0)).where(
                BotConfigurationVersion.bot_configuration_id == bot_configuration_id,
                BotConfigurationVersion.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def list_for_config(
        self, db: AsyncSession, bot_configuration_id: str
    ) -> list[BotConfigurationVersion]:
        result = await db.execute(
            select(BotConfigurationVersion)
            .where(
                BotConfigurationVersion.bot_configuration_id == bot_configuration_id,
                BotConfigurationVersion.deleted_at.is_(None),
            )
            .order_by(BotConfigurationVersion.version.desc())
        )
        return list(result.scalars().all())

    async def version_count_map(self, db: AsyncSession, config_ids: list[str]) -> dict[str, int]:
        """config_id → nº de versiones vivas (batch, para BotConfigurationItem.version_count)."""
        if not config_ids:
            return {}
        result = await db.execute(
            select(
                BotConfigurationVersion.bot_configuration_id,
                func.count(BotConfigurationVersion.id),
            )
            .where(
                BotConfigurationVersion.bot_configuration_id.in_(config_ids),
                BotConfigurationVersion.deleted_at.is_(None),
            )
            .group_by(BotConfigurationVersion.bot_configuration_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def numbers_by_ids(self, db: AsyncSession, version_ids: list[str]) -> dict[str, int]:
        """version_id → su número de versión (batch, para BotConfigurationItem.current_version_number)."""
        if not version_ids:
            return {}
        result = await db.execute(
            select(BotConfigurationVersion.id, BotConfigurationVersion.version).where(
                BotConfigurationVersion.id.in_(version_ids)
            )
        )
        return {row[0]: int(row[1]) for row in result.all()}


bot_configuration_version_repository = BotConfigurationVersionRepository()
