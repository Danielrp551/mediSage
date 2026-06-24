"""
Repo del singleton `dashboard_refresh_state` (observabilidad del job). NO extiende BaseRepository
(no necesita /list ni soft-delete). `get` lee la fila (None antes del 1er refresh — lo usa /meta,
NO crea). `get_singleton` la crea on-first-run y la devuelve (lo usa el refresh).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dashboards.models.dashboard_refresh_state import DashboardRefreshState
from app.shared.utils import generate_uuid, utc_now

_SYSTEM = "SYSTEM"  # actor del job (no hay user real); created_by/updated_by son audit, no FK


class DashboardRefreshStateRepository:
    async def get(self, db: AsyncSession) -> DashboardRefreshState | None:
        """La fila singleton, o None si el job nunca corrió (lectura para /meta — NO crea)."""
        return (await db.execute(select(DashboardRefreshState).limit(1))).scalars().first()

    async def get_singleton(self, db: AsyncSession) -> DashboardRefreshState:
        """La fila singleton; la crea on-first-run (la usa el refresh)."""
        existing = await self.get(db)
        if existing is not None:
            return existing
        now = utc_now()
        state = DashboardRefreshState(
            id=generate_uuid(),
            last_refreshed_at=None,
            window_days=0,
            status="ok",
            last_error=None,
            active=True,
            created_by=_SYSTEM,
            created_on=now,
            updated_by=_SYSTEM,
            updated_on=now,
        )
        db.add(state)
        await db.flush()
        return state


refresh_state_repository = DashboardRefreshStateRepository()
