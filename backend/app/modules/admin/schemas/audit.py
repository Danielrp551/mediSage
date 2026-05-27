"""
Shared audit response shapes.

Lives in its own module so any entity schema (User/Role/Permission/…) can
import `UserAuditInfo` without creating import cycles (a Role response
needs to resolve `created_by` to a User name, but User responses also
embed Roles — putting the audit shape in `user.py` would cycle).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class UserAuditInfo(BaseModel):
    """Compact actor info for audit columns — resolves `created_by`/`updated_by`
    UUIDs to a human-readable name in API responses. Null when the actor user
    has been hard-deleted or never existed (e.g. legacy bootstrap rows)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    email: EmailStr
