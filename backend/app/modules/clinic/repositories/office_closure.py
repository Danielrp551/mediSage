"""
OfficeClosure repository. `ALLOWED_FIELDS` whitelists columns the frontend could
filter/sort dynamically — though closures are read via `list_for_office` (range
overlap), not a generic /list endpoint. Soft-delete handled by `BaseRepository`
(reads filter `deleted_at IS NULL`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.office_closure import OfficeClosure
from app.shared.base_repository import BaseRepository


class OfficeClosureRepository(BaseRepository[OfficeClosure]):
    ALLOWED_FIELDS: set[str] = {"is_closed", "starts_at", "ends_at", "created_on"}

    def __init__(self) -> None:
        super().__init__(OfficeClosure)

    async def list_for_office(
        self,
        db: AsyncSession,
        office_id: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[OfficeClosure]:
        # Range overlap: a closure is in range if it starts before `to` AND ends
        # after `from` (half-open windows handled by the callers). Both bounds
        # are optional — no filter returns every non-deleted closure.
        stmt = (
            select(OfficeClosure)
            .where(
                OfficeClosure.office_id == office_id,
                OfficeClosure.deleted_at.is_(None),
            )
            .order_by(OfficeClosure.starts_at.asc())
        )
        if date_to is not None:
            stmt = stmt.where(OfficeClosure.starts_at < date_to)
        if date_from is not None:
            stmt = stmt.where(OfficeClosure.ends_at > date_from)
        result = await db.execute(stmt)
        return list(result.scalars().all())


office_closure_repository = OfficeClosureRepository()
