from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.admin.schemas.permission import PermissionOption


class RoleOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str = Field(..., min_length=1, max_length=255)
    permission_ids: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None
    permission_ids: list[str] | None = None


class RoleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    active: bool
    permissions_count: int
    created_by: str
    created_by_user: UserAuditInfo | None = None
    created_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
    updated_on: datetime


class RoleDetail(RoleItem):
    permissions: list[PermissionOption]
