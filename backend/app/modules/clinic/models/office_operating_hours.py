"""
OfficeOperatingHours = one recurring weekly time block of an office. An office
can have SEVERAL rows per day (morning + afternoon with a lunch gap); there is
deliberately NO unique on (office_id, day_of_week).

`day_of_week` follows the Python `datetime.weekday()` convention:
0 = Monday ... 6 = Sunday (NOT Postgres EXTRACT(DOW), which is 0 = Sunday). The
scheduling code is Python, so using the host-language convention avoids
off-by-one bugs. `opens_at`/`closes_at` are naive `time` (no TZ) interpreted in
`office.branch.timezone`. CHECK closes_at > opens_at: a block never crosses
midnight (model that as two blocks on two days).

Edited as an aggregate via the atomic bulk replace (PUT) — never per-row CRUD.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.clinic.models.office import Office


class OfficeOperatingHours(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "office_operating_hours"
    __table_args__ = (
        CheckConstraint("closes_at > opens_at", name="ck_office_hours_closes_after_opens"),
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_office_hours_day_of_week_range",
        ),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("office.id"), nullable=False, index=True
    )
    # 0=Mon .. 6=Sun (Python datetime.weekday()).
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    closes_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)

    office: Mapped[Office] = relationship(back_populates="operating_hours", lazy="raise")
