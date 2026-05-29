"""
Pydantic v2 schemas for OfficeClosure. Variants:
- OfficeClosureCreate: input (no Ellipsis, see backend.md).
- OfficeClosureItem: list row / single, with audit users.
- OfficeClosureDetail: same shape as Item (a closure has no relations to resolve).

There is deliberately NO Update variant: a closure is a small atomic unit
(range + flag + reason); to correct one, delete and recreate it. Validator
messages are English (422 details); user-facing Spanish lives in the frontend
Zod schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class OfficeClosureCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    is_closed: bool = True
    reason: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _ends_after_starts(self) -> OfficeClosureCreate:
        # Mirrors the DB CHECK (ends_at > starts_at).
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class OfficeClosureItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    office_id: str
    starts_at: datetime
    ends_at: datetime
    is_closed: bool
    reason: str
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class OfficeClosureDetail(OfficeClosureItem):
    """Same shape as Item — a closure has no relations to resolve."""
