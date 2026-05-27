from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo


class PermissionOption(BaseModel):
    """Compact shape used by dropdowns."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    module: str


class PermissionCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=255)
    module: str = Field(..., min_length=2, max_length=60)


class PermissionUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=255)
    module: str | None = Field(default=None, min_length=2, max_length=60)
    active: bool | None = None


class PermissionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str
    module: str
    active: bool
    created_by: str
    created_by_user: UserAuditInfo | None = None
    created_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
    updated_on: datetime
