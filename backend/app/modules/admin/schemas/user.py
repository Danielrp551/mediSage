from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.admin.schemas.permission import PermissionOption
from app.modules.admin.schemas.role import RoleOption


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    role_ids: list[str] = Field(default_factory=list)
    permission_ids: list[str] = Field(default_factory=list)
    # If omitted, the service generates a strong random password and the
    # response includes it once so the caller can deliver it out of band.
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    active: bool | None = None
    role_ids: list[str] | None = None
    permission_ids: list[str] | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    full_name: str
    first_name: str
    last_name: str
    second_last_name: str | None
    document_type: str | None
    document_number: str | None
    phone: str | None
    active: bool
    roles_count: int
    permissions_count: int
    created_by: str
    created_by_user: UserAuditInfo | None = None
    created_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
    updated_on: datetime


class UserDetail(UserItem):
    roles: list[RoleOption]
    permissions: list[PermissionOption]


class UserCreatedResponse(BaseModel):
    """Returned by POST /users — `generated_password` is set when the
    caller didn't supply one and we generated one."""

    success: bool = True
    data: UserDetail
    generated_password: str | None = None
