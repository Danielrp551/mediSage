"""
Pydantic v2 schemas for Product. Variants:
- ProductCreate / ProductUpdate: inputs (no Ellipsis, see backend.md).
- ProductItem: paginated row, with denormalized service_name + vertical_name.
- ProductDetail: Item + the parent service and vertical as Options.
- ProductOption: dropdowns / selects (carries price + duration for booking).

`code` and `service_id` are immutable after creation (stable slug; moving a
product between services would orphan appointments/promotions) — Update omits
both. The cross-field rule (duration required when bookable + has a cancel
deadline) is enforced on Create; partial Update can't see the merged state so
it relies on the frontend + the create-time guard.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.service import ServiceOption
from app.modules.catalog.schemas.vertical import VerticalOption

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,58}[a-z0-9]$")
ISO_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

MAX_DURATION_MIN = 24 * 60  # a single day
MAX_CANCEL_HOURS = 24 * 7  # a week


class ProductCreate(BaseModel):
    service_id: str = Field(min_length=1)
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    base_price: Decimal = Field(ge=Decimal("0"), max_digits=10, decimal_places=2)
    currency: str = Field(default="PEN", max_length=3)
    duration_min: int | None = Field(default=None, ge=1, le=MAX_DURATION_MIN)
    requires_appointment: bool = True
    is_package: bool = False
    min_hours_to_cancel: int | None = Field(default=None, ge=0, le=MAX_CANCEL_HOURS)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-60 chars)"
            )
        return v

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str) -> str:
        if not ISO_CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be ISO 4217 alpha-3 (e.g. PEN, USD)")
        return v

    @model_validator(mode="after")
    def _appointment_implies_duration(self) -> ProductCreate:
        # A bookable product with a cancellation deadline needs a duration so
        # scheduling can compute slots. NULL duration is allowed in general
        # (falls back to the doctor's slot length), but the combination
        # "requires_appointment + min_hours_to_cancel set + duration NULL" is
        # almost certainly a data-entry mistake, so reject it.
        if (
            self.requires_appointment
            and self.min_hours_to_cancel is not None
            and self.duration_min is None
        ):
            raise ValueError(
                "duration_min is required when requires_appointment=true "
                "and min_hours_to_cancel is set"
            )
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    base_price: Decimal | None = Field(
        default=None, ge=Decimal("0"), max_digits=10, decimal_places=2
    )
    currency: str | None = Field(default=None, max_length=3)
    duration_min: int | None = Field(default=None, ge=1, le=MAX_DURATION_MIN)
    requires_appointment: bool | None = None
    is_package: bool | None = None
    min_hours_to_cancel: int | None = Field(default=None, ge=0, le=MAX_CANCEL_HOURS)
    active: bool | None = None
    # NOT updatable: service_id (would orphan), code (stable slug).

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not ISO_CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be ISO 4217 alpha-3 (e.g. PEN, USD)")
        return v


class ProductItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str
    service_name: str  # denormalized
    vertical_id: str  # denormalized
    vertical_name: str  # denormalized
    code: str
    name: str
    description: str | None
    base_price: Decimal
    currency: str
    duration_min: int | None
    requires_appointment: bool
    is_package: bool
    min_hours_to_cancel: int | None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class ProductDetail(ProductItem):
    service: ServiceOption
    vertical: VerticalOption


class ProductOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str
    code: str
    name: str
    base_price: Decimal
    currency: str
    duration_min: int | None
