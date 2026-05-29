"""
OfficeClosure = an ad-hoc exception to the weekly pattern, covering BOTH cases
with one schema via `is_closed`:
  - is_closed=True  → office NOT available in the range (holiday, maintenance);
                      overrides the pattern.
  - is_closed=False → office IS available even if the pattern says otherwise
                      (e.g. open one Sunday on demand).

`starts_at`/`ends_at` are timestamptz (UTC on disk, ISO 8601 with offset in
JSON). CHECK ends_at > starts_at. scheduling interprets `is_closed` when it
combines closures with the recurring pattern. Edited as individual units (CRUD)
— to fix one, delete and recreate it (no Update variant).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
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


class OfficeClosure(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "office_closure"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_office_closure_ends_after_starts"),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("office.id"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    office: Mapped[Office] = relationship(back_populates="closures", lazy="raise")
