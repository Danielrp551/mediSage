"""
Schemas de disponibilidad on-the-fly (ADR-006/007): request/slot/response del cómputo
+ check-slot. NO persisten. `starts_at`/`ends_at` son timestamptz UTC; el browser los
renderiza en la TZ del branch.

`CalendarResponse` (grilla) llega en F4 (vive aquí junto a Availability*/CheckSlot*).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AvailabilityRequest(BaseModel):
    """Body de POST /availability/compute. branch_id/office_id opcionales acotan los
    offices candidatos; si faltan, se consideran todos los offices aptos del doctor.
    El rango [from_date, to_date] es inclusivo."""

    doctor_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    branch_id: str | None = None
    office_id: str | None = None
    from_date: date_type
    to_date: date_type

    @model_validator(mode="after")
    def _range_ok(self) -> AvailabilityRequest:
        if self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date")
        return self


class AvailabilitySlot(BaseModel):
    """Un slot libre concreto. starts_at/ends_at son timestamptz UTC. Denormaliza
    doctor/office/branch para que la grilla/wizard no joineen."""

    model_config = ConfigDict(from_attributes=True)
    starts_at: datetime
    ends_at: datetime
    doctor_id: str
    doctor_name: str
    office_id: str
    office_name: str
    branch_id: str
    branch_name: str


class AvailabilityResponse(BaseModel):
    slots: list[AvailabilitySlot] = Field(default_factory=list)
    duration_min: int  # la duración efectiva de la cita (de product, fallback doctor)
    doctor_slot_duration_min: int  # el grano del calendario del doctor


class CheckSlotRequest(BaseModel):
    """Body de POST /availability/check-slot — revalida UN slot puntual antes de book."""

    doctor_id: str = Field(min_length=1)
    office_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    scheduled_for: datetime  # inicio propuesto, UTC


class CheckSlotResponse(BaseModel):
    available: bool
    reason: str | None = None  # code del primer invariante que falla (None si available)
