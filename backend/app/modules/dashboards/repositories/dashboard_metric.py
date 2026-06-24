"""
PLANO DE LECTURA del rollup (caliente, por request). Suma `dashboard_daily_metric` por
rango+filtros; el group_by(segment) arma el desglose (donut/línea/embudo); el `value` nullable se
COALESCEa. Molde `marketing/repositories/promotion_usage.py:usage_summary` (func.count /
func.coalesce(func.sum(...), 0) / group_by). ALLOWED_FIELDS=set(): NO expone /list dinámico.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dashboards.models.dashboard_daily_metric import DashboardDailyMetric
from app.shared.base_repository import BaseRepository


class DashboardMetricRepository(BaseRepository[DashboardDailyMetric]):
    ALLOWED_FIELDS: set[str] = set()  # sin /list dinámico; las lecturas son agregaciones fijas

    def __init__(self) -> None:
        super().__init__(DashboardDailyMetric)

    def _range(
        self,
        q: Select[Any],
        *,
        metric: str,
        date_from: date,
        date_to: date,
        branch_id: str | None,
    ) -> Select[Any]:
        """Filtro base compartido: una métrica, el rango [date_from, date_to], y la sede.
        branch_id None = NO filtra por sede (suma clínica entera, incl. filas branch_id NULL).
        branch_id con valor = SOLO esa sede (las filas branch_id NULL — métricas de clínica —
        quedan fuera; por eso el funnel mezcla escalas con cuidado, ver metrics.py)."""
        q = q.where(
            DashboardDailyMetric.metric == metric,
            DashboardDailyMetric.metric_date >= date_from,
            DashboardDailyMetric.metric_date <= date_to,
        )
        if branch_id is not None:
            q = q.where(DashboardDailyMetric.branch_id == branch_id)
        return q

    async def sum_scalar(
        self,
        db: AsyncSession,
        *,
        metric: str,
        date_from: date,
        date_to: date,
        branch_id: str | None = None,
        segment: str | None = None,
    ) -> Row[tuple[int, Decimal]]:
        """Row(sum_count, sum_value) de UNA métrica en el rango. `segment` dado → ESE segmento;
        `segment=None` → la fila TOTAL (segment IS NULL), NO la suma de todos los segmentos:
        `conversations` tiene una fila total (NULL) + una subset ('bot') bajo la misma métrica →
        sumar todo doble-contaría. Las métricas puramente escalares (leads_created/customers_new/
        bot_turns/bot_cost) solo tienen fila NULL → `IS NULL` devuelve su total igual. coalesce evita
        NULL cuando no hay filas (rollup vacío → 0, NO error — §8)."""
        q = self._range(
            select(
                func.coalesce(func.sum(DashboardDailyMetric.count), 0),
                func.coalesce(func.sum(DashboardDailyMetric.value), 0),
            ),
            metric=metric,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
        )
        if segment is not None:
            q = q.where(DashboardDailyMetric.segment == segment)
        else:
            q = q.where(DashboardDailyMetric.segment.is_(None))
        return (await db.execute(q)).one()

    async def sum_by_segment(
        self,
        db: AsyncSession,
        *,
        metric: str,
        date_from: date,
        date_to: date,
        branch_id: str | None = None,
    ) -> dict[str, int]:
        """{segment: sum_count} — el desglose del DONUT (appointments por status_code) y del
        EMBUDO de lead (lead_stage por lead_status_code). Las filas con segment NULL (escalares)
        se agrupan bajo la clave '' (el caller las ignora)."""
        q = self._range(
            select(
                DashboardDailyMetric.segment,
                func.coalesce(func.sum(DashboardDailyMetric.count), 0),
            ),
            metric=metric,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
        ).group_by(DashboardDailyMetric.segment)
        return {(row[0] or ""): row[1] for row in (await db.execute(q)).all()}

    async def sum_by_date_segment(
        self,
        db: AsyncSession,
        *,
        metric: str,
        date_from: date,
        date_to: date,
        branch_id: str | None = None,
    ) -> dict[tuple[date, str], int]:
        """{(metric_date, segment): sum_count} — la LÍNEA de evolución (lead_stage por día ×
        lead_status_code). El service bucketiza a TimeSeriesPoint rellenando los días faltantes."""
        q = self._range(
            select(
                DashboardDailyMetric.metric_date,
                DashboardDailyMetric.segment,
                func.coalesce(func.sum(DashboardDailyMetric.count), 0),
            ),
            metric=metric,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
        ).group_by(DashboardDailyMetric.metric_date, DashboardDailyMetric.segment)
        return {(row[0], row[1] or ""): row[2] for row in (await db.execute(q)).all()}

    async def delete_window(self, db: AsyncSession, *, date_from: date, date_to: date) -> None:
        """Refresh paso 0: borra la ventana móvil ANTES de reinsertar (idempotencia sin ON CONFLICT
        sobre columnas nullables — branch_id/segment NULL no chocan en un UNIQUE). DELETE real (la
        tabla es derivada, sin SoftDelete)."""
        await db.execute(
            delete(DashboardDailyMetric).where(
                DashboardDailyMetric.metric_date >= date_from,
                DashboardDailyMetric.metric_date <= date_to,
            )
        )


dashboard_metric_repository = DashboardMetricRepository()
