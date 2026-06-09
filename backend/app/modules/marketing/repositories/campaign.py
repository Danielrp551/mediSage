"""
Campaign repository. `ALLOWED_FIELDS` whitelista las columnas REALES que el frontend
puede filtrar/ordenar (lección cd10c78: NUNCA denormalizados como target_vertical_name
ni promotions_count). Soft-delete lo maneja `BaseRepository` (todo read filtra
`deleted_at IS NULL`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.marketing.models.campaign import Campaign
from app.shared.base_repository import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "status",
        "start_date",
        "end_date",
        "target_vertical_id",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Campaign)

    async def get_by_code(self, db: AsyncSession, code: str) -> Campaign | None:
        result = await db.execute(
            select(Campaign).where(Campaign.code == code, Campaign.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Campaign]:
        """status='active' + vivos, order name. GET /campaigns/active (lista cruda)."""
        result = await db.execute(
            select(Campaign)
            .where(
                Campaign.status == "active",
                Campaign.active.is_(True),
                Campaign.deleted_at.is_(None),
            )
            .order_by(Campaign.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Campaign]:
        """Batch (patrón vertical_repository.get_by_ids)."""
        if not ids:
            return []
        result = await db.execute(
            select(Campaign).where(Campaign.id.in_(ids), Campaign.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def campaign_name_map(self, db: AsyncSession, ids: list[str]) -> dict[str, str]:
        """Batch id→name para denormalizar campaign_name (lo consume PromotionUsage en F3)."""
        if not ids:
            return {}
        result = await db.execute(
            select(Campaign.id, Campaign.name).where(
                Campaign.id.in_(ids), Campaign.deleted_at.is_(None)
            )
        )
        return {row[0]: row[1] for row in result.all()}


campaign_repository = CampaignRepository()
