"""
Pydantic v2 schemas for Office. Variants:
- OfficeCreate / OfficeUpdate: inputs (no Ellipsis, see backend.md).
- OfficeItem: paginated row, with denormalized `branch_name` + verticals_count.
- OfficeDetail: Item + the parent branch (Option) + the apt verticals.
- OfficeOption: dropdowns / selects.

`code` and `branch_id` are immutable after creation: `code` is a stable
per-branch identifier, and moving an office between branches would orphan its
hours/closures coordinates — Update intentionally omits both. Validator
messages are English (422 details); user-facing Spanish lives in the frontend
Zod schema.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.clinic.schemas.branch import BranchOption

# Office codes are short identifiers ("C-03", "ESTETICA-01"): letters/digits
# with - and _. Looser than catalog slugs on purpose (uppercase + hyphen ok).
CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,38}[A-Za-z0-9]$")


class OfficeCreate(BaseModel):
    branch_id: str = Field(min_length=1)
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    room_number: str | None = Field(default=None, max_length=20)
    floor: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    vertical_ids: list[str] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be 2-40 chars: letters/digits/-/_, start and end with a letter or digit"
            )
        return v

    @field_validator("vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("vertical_ids must not contain duplicates")
        return v


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    room_number: str | None = Field(default=None, max_length=20)
    floor: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    # Full M:N replace when present; omit to leave the apt verticals untouched.
    vertical_ids: list[str] | None = None
    active: bool | None = None
    # NOT updatable: branch_id (would move the office between sites and orphan
    # its hours/closures coordinates), code (stable per-branch identifier).

    @field_validator("vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("vertical_ids must not contain duplicates")
        return v


class OfficeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    branch_id: str
    branch_name: str  # denormalized for table rows (avoids a drawer fetch)
    code: str
    name: str
    room_number: str | None
    floor: str | None
    description: str | None
    active: bool
    verticals_count: int  # denormalized count of apt (non-deleted) verticals
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class OfficeDetail(OfficeItem):
    branch: BranchOption
    verticals: list[VerticalOption]  # soft-deleted verticals filtered out


class OfficeOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    branch_id: str
    code: str
    name: str
