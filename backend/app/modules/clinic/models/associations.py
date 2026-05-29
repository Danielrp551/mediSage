"""
Many-to-many association tables for the clinic module. Kept in a single
file so SQLAlchemy sees them before the related models import (template
convention — admin/models/associations.py does the same with user_role).

`office_vertical` links an Office to the catalog Verticals it is fit to
host. The FK to `vertical.id` is RESTRICT (default, no ondelete) — a
hard-deleted vertical must not silently orphan the association; catalog's
soft-delete is the normal path and is filtered out at query time, not
enforced here (no coupling to catalog's delete guard).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

office_vertical = Table(
    "office_vertical",
    Base.metadata,
    Column(
        "office_id",
        String(36),
        ForeignKey("office.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "vertical_id",
        String(36),
        ForeignKey("vertical.id"),  # RESTRICT — no ondelete cascade to catalog
        primary_key=True,
    ),
)
