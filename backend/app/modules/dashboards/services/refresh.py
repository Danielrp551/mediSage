"""
Plano de CÓMPUTO (frío, por cron). Recalcula el rollup sobre la VENTANA MÓVIL
[hoy - WINDOW_DAYS, hoy] + el día en curso, agregando las fuentes (source_aggregation_repository)
y reescribiendo dashboard_daily_metric (DELETE de la ventana + INSERT — idempotente, sin
ON CONFLICT sobre columnas nullables). Setea dashboard_refresh_state (status/last_refreshed_at).
Es el ÚNICO punto que escanea las fuentes. Lo dispara Cloud Scheduler vía /internal/refresh.

NUNCA propaga un 5xx: ante un fallo de agregación marca status='error' + last_error y devuelve
RefreshResult(status="error") con 200 (el panel sirve el último rollup bueno + el badge crece —
degrada con gracia, design §13).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.dashboards.enums import DashboardMetric
from app.modules.dashboards.models.dashboard_daily_metric import DashboardDailyMetric
from app.modules.dashboards.repositories.dashboard_metric import dashboard_metric_repository
from app.modules.dashboards.repositories.dashboard_refresh_state import refresh_state_repository
from app.modules.dashboards.repositories.source_aggregation import source_aggregation_repository
from app.modules.dashboards.schemas.refresh import RefreshResult
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now

logger = logging.getLogger(__name__)

_SYSTEM = "SYSTEM"  # actor del job (no hay user real)


def _as_date(value: date | str) -> date:
    """func.date() devuelve un objeto date en Postgres y un str 'YYYY-MM-DD' en sqlite (smoke)
    → normalizar a date para el modelo (lección §13 sqlite vs Postgres)."""
    return date.fromisoformat(value) if isinstance(value, str) else value


def _row(
    metric_date: date | str,
    branch_id: str | None,
    metric: DashboardMetric,
    segment: str | None,
    count: int,
    *,
    value: Decimal | None = None,
) -> DashboardDailyMetric:
    now = utc_now()
    return DashboardDailyMetric(
        id=generate_uuid(),
        metric_date=_as_date(metric_date),
        branch_id=branch_id,
        metric=str(metric),
        segment=segment,
        count=count,
        value=value,
        active=True,
        created_by=_SYSTEM,
        created_on=now,
        updated_by=_SYSTEM,
        updated_on=now,
    )


async def run_refresh(db: AsyncSession) -> SingleResponse[RefreshResult]:
    settings = get_settings()
    window = settings.DASHBOARD_REFRESH_WINDOW_DAYS
    now = utc_now()
    date_to = now.date()
    date_from = date_to - timedelta(days=window)
    since = datetime(date_from.year, date_from.month, date_from.day, tzinfo=now.tzinfo)
    until = now  # hasta el instante actual (incluye el día en curso)

    state = await refresh_state_repository.get_singleton(db)
    state.status = "running"
    state.window_days = window
    state.updated_on = now
    await db.flush()

    try:
        # 0) borra la ventana móvil (idempotencia sin ON CONFLICT).
        await dashboard_metric_repository.delete_window(db, date_from=date_from, date_to=date_to)
        rows: list[DashboardDailyMetric] = []

        # 1) agrega cada métrica de las fuentes → filas del rollup.
        for d, c in await source_aggregation_repository.conversations_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.conversations, None, c))
        for d, c in await source_aggregation_repository.conversations_bot_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.conversations, "bot", c))
        for d, c in await source_aggregation_repository.leads_created_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.leads_created, None, c))
        for d, code, c in await source_aggregation_repository.lead_stage_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.lead_stage, code, c))
        for d, branch, code, c in await source_aggregation_repository.appointments_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, branch, DashboardMetric.appointments, code, c))
        for d, branch, src, c in await source_aggregation_repository.appointments_source_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, branch, DashboardMetric.appointments_source, src, c))
        for d, c in await source_aggregation_repository.customers_new_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.customers_new, None, c))
        for d, c in await source_aggregation_repository.bot_turns_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.bot_turns, None, c))
        for d, tokens, cost in await source_aggregation_repository.bot_cost_by_day(
            db, since=since, until=until
        ):
            rows.append(_row(d, None, DashboardMetric.bot_cost, None, tokens, value=cost))

        db.add_all(rows)
        await db.flush()
        state.status = "ok"
        state.last_refreshed_at = now
        state.last_error = None
        state.updated_on = utc_now()
        await db.flush()
        return SingleResponse(
            data=RefreshResult(
                refreshed_at=now.isoformat(),
                window_days=window,
                rows_written=len(rows),
                status="ok",
            )
        )
    except Exception as exc:  # noqa: BLE001 — el job marca error y devuelve 'error' (NO 5xx silencioso)
        logger.exception("dashboards.refresh.failed")
        await db.rollback()
        state = await refresh_state_repository.get_singleton(db)
        state.status = "error"
        state.last_error = str(exc)[:500]
        state.updated_on = utc_now()
        await db.flush()
        return SingleResponse(
            data=RefreshResult(
                refreshed_at=now.isoformat(), window_days=window, rows_written=0, status="error"
            )
        )
