"""
ChannelAccount repository. `ALLOWED_FIELDS` = whitelist de columnas REALES
filtrable/ordenable desde el frontend (lección hotfix `cd10c78` de staff: nunca
campos denormalizados). Soft-delete lo maneja `BaseRepository` (cada read filtra
`deleted_at IS NULL`).

`get_by_external_id` respalda el guard de unicidad (409
CHANNEL_ACCOUNT_EXTERNAL_TAKEN). El webhook (F2) carga la cuenta por **id**
(`get_by_id` del BaseRepository, viene en la URL), no por external_id.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.models.channel_account import ChannelAccount
from app.shared.base_repository import BaseRepository


class ChannelAccountRepository(BaseRepository[ChannelAccount]):
    ALLOWED_FIELDS: set[str] = {
        "channel_type",
        "name",
        "external_identifier",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(ChannelAccount)

    async def get_by_external_id(
        self, db: AsyncSession, channel_type: str, external_identifier: str
    ) -> ChannelAccount | None:
        """Resuelve la cuenta viva por (channel_type, external_identifier).
        Respalda el guard de unicidad (409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN)."""
        result = await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.channel_type == channel_type,
                ChannelAccount.external_identifier == external_identifier,
                ChannelAccount.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[ChannelAccount]:
        """Cuentas vivas y habilitadas, ordenadas por nombre (dropdowns/filtros)."""
        result = await db.execute(
            select(ChannelAccount)
            .where(ChannelAccount.active.is_(True), ChannelAccount.deleted_at.is_(None))
            .order_by(ChannelAccount.name.asc())
        )
        return list(result.scalars().all())


channel_account_repository = ChannelAccountRepository()
