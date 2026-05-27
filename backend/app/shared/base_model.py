"""
Mixins shared by all domain tables: UUID PK, soft delete, audit columns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    """Timezone-aware UTC. Stored via `DateTime(timezone=True)` (timestamptz)."""
    return datetime.now(timezone.utc)


class PrimaryKeyMixin:
    """Random UUID string PK. Same shape as `created_by` audit columns."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    """
    Audit columns. `created_by` / `updated_by` carry the actor's user id,
    populated by services (they have access to the current user); never
    set automatically — passing it explicitly keeps the trail honest.
    """

    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False)


class SoftDeleteMixin:
    """`deleted_at IS NULL` means alive. `BaseRepository` filters on this."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class ActiveMixin:
    """Business "enabled/disabled" toggle (distinct from soft delete)."""

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
