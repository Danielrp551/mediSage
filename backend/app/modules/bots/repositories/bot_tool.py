"""
BotTool repository. `ALLOWED_FIELDS` = whitelist filtrable/ordenable: SOLO columnas reales
(lección hotfix cd10c78); el denormalizado `is_registered` NO. Incluye los helpers del M:N
bot_configuration_tool (lectura por `bot_configuration_id`, set bulk reemplazando el conjunto)
— se lee/escribe la Table directamente, sin `relationship(secondary=...)` (patrón crm/conversations:
acceso explícito, sin N+1 silencioso).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.associations import bot_configuration_tool
from app.modules.bots.models.bot_tool import BotTool
from app.shared.base_repository import BaseRepository


class BotToolRepository(BaseRepository[BotTool]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "target_service",
        "requires_confirmation",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(BotTool)

    async def get_by_code(self, db: AsyncSession, code: str) -> BotTool | None:
        """Resuelve la tool VIVA por code. Respalda el guard 409 BOT_TOOL_CODE_TAKEN."""
        result = await db.execute(
            select(BotTool).where(BotTool.code == code, BotTool.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[BotTool]:
        result = await db.execute(
            select(BotTool)
            .where(BotTool.active.is_(True), BotTool.deleted_at.is_(None))
            .order_by(BotTool.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, tool_ids: Sequence[str]) -> list[BotTool]:
        """Tools VIVAS (no soft-deleted) cuyos id están en `tool_ids`. Para validar el set del
        M:N (BOT_TOOL_NOT_FOUND) y para hidratar las Options asignadas a un bot."""
        if not tool_ids:
            return []
        result = await db.execute(
            select(BotTool).where(BotTool.id.in_(list(tool_ids)), BotTool.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def tool_ids_for_config(self, db: AsyncSession, bot_configuration_id: str) -> list[str]:
        """Los bot_tool_id VIVOS (no soft-deleted) asignados a un bot. JOIN con bot_tool para
        excluir tools soft-deleted (la tabla M:N no tiene deleted_at) → `Detail.tool_ids` queda
        consistente con `GET /{id}/tools` (ambos = tools vivas asignadas), sin contar fantasmas."""
        result = await db.execute(
            select(bot_configuration_tool.c.bot_tool_id)
            .join(BotTool, BotTool.id == bot_configuration_tool.c.bot_tool_id)
            .where(
                bot_configuration_tool.c.bot_configuration_id == bot_configuration_id,
                BotTool.deleted_at.is_(None),
            )
        )
        return [row[0] for row in result.all()]

    async def active_tools_for_config(
        self, db: AsyncSession, bot_configuration_id: str
    ) -> list[BotTool]:
        """Las BotTool VIVAS y activas de un bot (las que ve el engine al armar el prompt).
        JOIN M:N + filtro active/deleted_at."""
        result = await db.execute(
            select(BotTool)
            .join(
                bot_configuration_tool,
                bot_configuration_tool.c.bot_tool_id == BotTool.id,
            )
            .where(
                bot_configuration_tool.c.bot_configuration_id == bot_configuration_id,
                BotTool.active.is_(True),
                BotTool.deleted_at.is_(None),
            )
            .order_by(BotTool.name.asc())
        )
        return list(result.scalars().all())

    async def set_config_tools(
        self, db: AsyncSession, bot_configuration_id: str, tool_ids: Sequence[str]
    ) -> None:
        """Reemplaza el conjunto de tools del bot (delete-all + insert; misma tx). Molde del
        editor de matriz de crm. NO valida existencia acá — el service valida que los tool_ids
        existan (BOT_TOOL_NOT_FOUND) antes de llamar."""
        await db.execute(
            delete(bot_configuration_tool).where(
                bot_configuration_tool.c.bot_configuration_id == bot_configuration_id
            )
        )
        for tid in dict.fromkeys(tool_ids):  # dedup preservando orden
            await db.execute(
                insert(bot_configuration_tool).values(
                    bot_configuration_id=bot_configuration_id, bot_tool_id=tid
                )
            )


bot_tool_repository = BotToolRepository()
