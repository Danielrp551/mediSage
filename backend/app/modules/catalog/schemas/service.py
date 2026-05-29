"""
Pydantic v2 schemas for Service. Variants:
- ServiceCreate / ServiceUpdate: inputs (no Ellipsis, see backend.md).
- ServiceItem: paginated row, with denormalized `vertical_name` + counts.
- ServiceDetail: Item + the parent vertical resolved as an Option.
- ServiceOption: dropdowns / selects.

`code` and `vertical_id` are immutable after creation: `code` is a stable
slug used by bots/reports, and moving a service between verticals would
orphan its products — Update intentionally omits both.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,58}[a-z0-9]$")


class ServiceCreate(BaseModel):
    vertical_id: str = Field(min_length=1)
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    display_order: int = Field(default=0, ge=0, le=9999)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-60 chars)"
            )
        return v


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    display_order: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None
    # NOT updatable: vertical_id (would orphan products), code (stable slug).


class ServiceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    vertical_id: str
    vertical_name: str  # denormalized for table rows (avoids a drawer fetch)
    code: str
    name: str
    description: str | None
    display_order: int
    active: bool
    products_count: int
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class ServiceDetail(ServiceItem):
    vertical: VerticalOption


class ServiceOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    vertical_id: str
    code: str
    name: str
