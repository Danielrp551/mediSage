"""
BotConfiguration repository. `ALLOWED_FIELDS` = whitelist filtrable/ordenable: SOLO columnas
reales (lección hotfix cd10c78); los denormalizados (current_version_number, version_count) NO.
`defaultSort` de configurations = created_on desc (spec §6).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_configuration import BotConfiguration
from app.shared.base_repository import BaseRepository


class BotConfigurationRepository(BaseRepository[BotConfiguration]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "bot_type",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(BotConfiguration)

    async def get_by_code(self, db: AsyncSession, code: str) -> BotConfiguration | None:
        """Resuelve el bot VIVO por code. Respalda el guard 409 BOT_CONFIGURATION_CODE_TAKEN."""
        result = await db.execute(
            select(BotConfiguration).where(
                BotConfiguration.code == code,
                BotConfiguration.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[BotConfiguration]:
        result = await db.execute(
            select(BotConfiguration)
            .where(BotConfiguration.active.is_(True), BotConfiguration.deleted_at.is_(None))
            .order_by(BotConfiguration.name.asc())
        )
        return list(result.scalars().all())


bot_configuration_repository = BotConfigurationRepository()
