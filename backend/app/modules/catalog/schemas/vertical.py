"""
Pydantic v2 schemas for Vertical. Variants:
- VerticalCreate / VerticalUpdate: inputs (no Ellipsis, see backend.md).
- VerticalItem: paginated row, with denormalized counts.
- VerticalDetail: same as Item (no extra relations to load).
- VerticalOption: dropdowns / selects.

`code` is immutable after creation: it's a stable slug used by bots and
reports — Update intentionally omits it.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class VerticalCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=60)
    display_order: int = Field(default=0, ge=0, le=9999)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-40 chars)"
            )
        return v

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not HEX_COLOR_PATTERN.fullmatch(v):
            raise ValueError("color must be hex like #RRGGBB")
        return v.upper()


class VerticalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=60)
    display_order: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not HEX_COLOR_PATTERN.fullmatch(v):
            raise ValueError("color must be hex like #RRGGBB")
        return v.upper()


class VerticalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    icon: str | None
    display_order: int
    active: bool
    services_count: int
    products_count: int
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class VerticalDetail(VerticalItem):
    """Same shape as Item — no extra relations to load yet."""


class VerticalOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    icon: str | None = None
