"""
OfficeOperatingHours repository. Not filtered/sorted dynamically — read via
`list_for_office`, written via the atomic bulk replace in the service.
`ALLOWED_FIELDS` stays empty (there is no /list endpoint for this resource).
Soft-delete handled by `BaseRepository` (reads filter `deleted_at IS NULL`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours
from app.shared.base_repository import BaseRepository


class OfficeOperatingHoursRepository(BaseRepository[OfficeOperatingHours]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(OfficeOperatingHours)

    async def list_for_office(self, db: AsyncSession, office_id: str) -> list[OfficeOperatingHours]:
        result = await db.execute(
            select(OfficeOperatingHours)
            .where(
                OfficeOperatingHours.office_id == office_id,
                OfficeOperatingHours.deleted_at.is_(None),
            )
            .order_by(
                OfficeOperatingHours.day_of_week.asc(),
                OfficeOperatingHours.opens_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def soft_delete_for_office(self, db: AsyncSession, office_id: str) -> None:
        """Retire ALL current live blocks of an office, used by the atomic bulk
        replace right before inserting the new set. Soft-delete (not hard) keeps
        the entity uniform with the rest of the template — every model carries
        SoftDeleteMixin and BaseRepository reads filter `deleted_at IS NULL`, so
        the retired pattern simply disappears from reads. Weekly patterns change
        rarely, so row accumulation is negligible, and the retired rows double as
        a cheap audit trail of past schedules."""
        rows = await self.list_for_office(db, office_id)
        for row in rows:
            await self.soft_delete(db, row)


office_operating_hours_repository = OfficeOperatingHoursRepository()
