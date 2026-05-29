"""
Pydantic v2 schemas for Branch. Variants:
- BranchCreate / BranchUpdate: inputs (no Ellipsis, see backend.md).
- BranchItem: paginated row, with denormalized offices_count.
- BranchDetail: same as Item (no extra relations to resolve in the drawer).
- BranchOption: dropdowns / selects.

`code` is immutable after creation: a stable slug used in internal URLs and by
bots — Update intentionally omits it. Validator messages are English (422
details); user-facing Spanish lives in the frontend Zod schema.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
# Cheap IANA sanity check ("Area/Location"); full validation is the OS tz db's
# job, done by scheduling when it resolves a local time.
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z]+/[A-Za-z_+\-/]+$")


class BranchCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    address_line: str = Field(min_length=1, max_length=255)
    district: str | None = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str = Field(default="PE", min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="America/Lima", min_length=3, max_length=60)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-40 chars)"
            )
        return v

    @field_validator("country")
    @classmethod
    def _iso_country(cls, v: str) -> str:
        v = v.upper()
        if not COUNTRY_PATTERN.fullmatch(v):
            raise ValueError("country must be ISO 3166-1 alpha-2 (e.g. PE, MX)")
        return v

    @field_validator("timezone")
    @classmethod
    def _iana_tz(cls, v: str) -> str:
        if not TIMEZONE_PATTERN.fullmatch(v):
            raise ValueError("timezone must be an IANA name like America/Lima")
        return v


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    district: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, min_length=3, max_length=60)
    active: bool | None = None
    # NOT updatable: code (stable slug used in URLs and by bots).

    @field_validator("country")
    @classmethod
    def _iso_country(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.upper()
        if not COUNTRY_PATTERN.fullmatch(v):
            raise ValueError("country must be ISO 3166-1 alpha-2 (e.g. PE, MX)")
        return v

    @field_validator("timezone")
    @classmethod
    def _iana_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not TIMEZONE_PATTERN.fullmatch(v):
            raise ValueError("timezone must be an IANA name like America/Lima")
        return v


class BranchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    address_line: str
    district: str | None
    city: str
    region: str | None
    country: str
    postal_code: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    phone: str | None
    email: str | None
    timezone: str
    active: bool
    offices_count: int  # denormalized for table rows (avoids a drawer fetch)
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class BranchDetail(BranchItem):
    """Same shape as Item — a branch has no extra relations to resolve in the
    drawer (offices live behind the Offices list filtered by branch_id)."""


class BranchOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    city: str | None = None
    timezone: str | None = None
