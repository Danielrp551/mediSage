"""
Many-to-many association tables. Keep them in a single file so SQLAlchemy
sees them before the related models import.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", String(36), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
)

role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", String(36), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        String(36),
        ForeignKey("permission.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_permission = Table(
    "user_permission",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        String(36),
        ForeignKey("permission.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
