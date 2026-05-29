"""
OfficeOperatingHours service. Module of functions (no classes), per template
convention. The weekly pattern is a value aggregate of the office, managed with
an atomic bulk replace (no per-row CRUD).

`replace` runs entirely inside the request transaction (get_db commits at the
end): it soft-deletes the live blocks then inserts the new set, so there is
never an intermediate state where "afternoon was deleted before the new one was
created" is observable. If Pydantic validation (overlap, closes>opens) or a DB
CHECK fails, the whole transaction rolls back and the previous pattern stays
intact.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours
from app.modules.clinic.repositories.office import office_repository
from app.modules.clinic.repositories.office_operating_hours import (
    office_operating_hours_repository,
)
from app.modules.clinic.schemas.office_operating_hours import (
    OfficeOperatingHoursItem,
    OfficeOperatingHoursReplace,
)
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


async def _require_office(db: AsyncSession, office_id: str) -> None:
    office = await office_repository.get_by_id(db, office_id)
    if office is None:
        raise NotFoundException("Consultorio no encontrado", code="OFFICE_NOT_FOUND")


async def list_for_office(
    db: AsyncSession, office_id: str
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    await _require_office(db, office_id)
    rows = await office_operating_hours_repository.list_for_office(db, office_id)
    return SingleResponse(
        data=[OfficeOperatingHoursItem.model_validate(r, from_attributes=True) for r in rows]
    )


async def replace(
    db: AsyncSession,
    office_id: str,
    payload: OfficeOperatingHoursReplace,
    *,
    actor_id: str,
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    await _require_office(db, office_id)

    # 1) Retire the current pattern (soft-delete the live rows). BaseRepository
    #    reads filter deleted_at, so the old blocks vanish from subsequent reads.
    await office_operating_hours_repository.soft_delete_for_office(db, office_id)

    # 2) Insert the new set. The whole thing runs in ONE request transaction, so
    #    there is never an intermediate visible state.
    now = utc_now()
    for block in payload.hours:
        db.add(
            OfficeOperatingHours(
                id=generate_uuid(),
                office_id=office_id,
                day_of_week=block.day_of_week,
                opens_at=block.opens_at,
                closes_at=block.closes_at,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
    await db.flush()

    # 3) Return the resulting pattern (re-read, ordered by day then opens_at).
    rows = await office_operating_hours_repository.list_for_office(db, office_id)
    return SingleResponse(
        data=[OfficeOperatingHoursItem.model_validate(r, from_attributes=True) for r in rows]
    )
