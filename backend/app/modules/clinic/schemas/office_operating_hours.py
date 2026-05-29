"""
Pydantic v2 schemas for OfficeOperatingHours. The weekly pattern is managed as
an aggregate via the atomic bulk replace — there is no per-row Create/Update.

- OfficeOperatingHoursItem: one weekly block, used both in the bulk replace body
  and in the GET/PUT response (`id` optional so the same shape serves in/out).
- OfficeOperatingHoursReplace: body of PUT /offices/{id}/operating-hours.

Validator messages are English (422 details); user-facing Spanish lives in the
frontend Zod schema.
"""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_DAY = 0  # Monday (Python datetime.weekday())
MAX_DAY = 6  # Sunday


class OfficeOperatingHoursItem(BaseModel):
    """One weekly block. `id` is optional so the same shape serves input and
    output (the bulk replace ignores any incoming id and assigns a fresh one)."""

    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    day_of_week: int = Field(ge=MIN_DAY, le=MAX_DAY)
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def _closes_after_opens(self) -> OfficeOperatingHoursItem:
        # Mirrors the DB CHECK (closes_at > opens_at). A block never crosses
        # midnight; if business needs that, model two blocks on two days.
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be later than opens_at")
        return self


class OfficeOperatingHoursReplace(BaseModel):
    """Body of the atomic bulk PUT /offices/{id}/operating-hours. The full weekly
    pattern is replaced as one aggregate — no per-block CRUD. Send {"hours": []}
    to clear the whole pattern."""

    hours: list[OfficeOperatingHoursItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_overlaps(self) -> OfficeOperatingHoursReplace:
        # Multiple blocks per day are allowed (morning + afternoon), but two
        # blocks on the same day must not overlap — that's an inconsistent
        # pattern the bulk replace should reject up front. Adjacent blocks
        # (next_open == prev_close) are fine.
        by_day: dict[int, list[tuple[time, time]]] = {}
        for h in self.hours:
            by_day.setdefault(h.day_of_week, []).append((h.opens_at, h.closes_at))
        for day, blocks in by_day.items():
            blocks.sort()
            # zip over consecutive pairs; lengths differ by 1 by design.
            for (_, prev_close), (next_open, _) in zip(blocks, blocks[1:], strict=False):
                if next_open < prev_close:
                    raise ValueError(
                        f"overlapping blocks on day_of_week={day} (Python weekday: 0=Mon)"
                    )
        return self
