"""
Generic async repository. Subclasses pass their model + an `ALLOWED_FIELDS`
set that gates dynamic filter/sort columns.

Soft-delete aware: every read filters `deleted_at IS NULL` automatically;
`delete()` is a soft delete by default.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from app.core.database import Base
from app.shared.base_schemas import QueryRequest
from app.shared.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sorting,
    build_count_query,
)

ModelT = TypeVar("ModelT", bound=Base)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BaseRepository(Generic[ModelT]):
    """
    Subclasses should set `ALLOWED_FIELDS` (used by `get_paginated`):

        class UserRepository(BaseRepository[User]):
            ALLOWED_FIELDS = {"email", "first_name", "last_name", "active", "created_on"}
            def __init__(self) -> None:
                super().__init__(User)
    """

    ALLOWED_FIELDS: set[str] = set()

    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    # ── Read ──

    async def get_by_id(
        self,
        db: AsyncSession,
        id: Any,
        *,
        include_deleted: bool = False,
        load: Sequence[ExecutableOption] | None = None,
    ) -> ModelT | None:
        q = select(self.model).where(self.model.id == id)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            q = q.where(self.model.deleted_at.is_(None))
        if load:
            q = q.options(*load)
        return (await db.execute(q)).scalars().first()

    async def get_paginated(
        self,
        db: AsyncSession,
        query_request: QueryRequest,
        *,
        load: Sequence[ExecutableOption] | None = None,
    ) -> tuple[list[ModelT], int]:
        q = select(self.model)
        if hasattr(self.model, "deleted_at"):
            q = q.where(self.model.deleted_at.is_(None))
        if load:
            q = q.options(*load)
        q = apply_filters(q, self.model, query_request.filters, self.ALLOWED_FIELDS)
        q = apply_sorting(q, self.model, query_request.sorting, self.ALLOWED_FIELDS)
        q = apply_pagination(q, query_request.pagination)

        items = list((await db.execute(q)).scalars().all())

        count_q = build_count_query(self.model, query_request.filters, self.ALLOWED_FIELDS)
        if hasattr(self.model, "deleted_at"):
            count_q = count_q.where(self.model.deleted_at.is_(None))
        total = (await db.execute(count_q)).scalar() or 0
        return items, total

    # ── Write ──

    async def create(self, db: AsyncSession, obj: ModelT) -> ModelT:
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def update(self, db: AsyncSession, obj: ModelT, changes: dict[str, Any]) -> ModelT:
        for k, v in changes.items():
            setattr(obj, k, v)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def soft_delete(self, db: AsyncSession, obj: ModelT) -> None:
        if not hasattr(obj, "deleted_at"):
            raise RuntimeError(f"{type(obj).__name__} has no `deleted_at` column")
        obj.deleted_at = _utc_now()  # type: ignore[attr-defined]
        await db.flush()
