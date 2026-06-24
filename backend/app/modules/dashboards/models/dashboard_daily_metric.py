"""
DashboardDailyMetric = la fact table del rollup diario (capa de agregación materializada).
Una fila por (metric_date, branch_id, metric, segment): el grano universal
(día × sede × métrica × segmento) → conteo/valor que cubre embudo, donut, línea y KPIs.
NO es una entidad de negocio: la repuebla el job de refresh agregando las fuentes
(crm/scheduling/conversations/bots). PK·A·T, SIN SoftDelete (derivada, upsert idempotente).

- branch_id NULLABLE = métrica a nivel CLÍNICA (conversaciones, leads, clientes, bot); con valor
  = métrica de CITAS por sede (solo `appointment` tiene branch_id). FK LÓGICA a clinic.branch
  SIN constraint (ADR-009): el rollup se trunca/reescribe; un branch borrado no rompe un INSERT.
- segment NULLABLE = desglose dentro de la métrica (status_code / lead_status_code / source /
  'bot'); NULL = métrica escalar.
- value Numeric(12,2) NULLABLE = monto/valor agregado (costo del bot, ingreso); NULL cuando la
  métrica es solo de conteo. Serializa como STRING en el wire.

UNIQUE (metric_date, branch_id, metric, segment) = el grano. ⚠ branch_id/segment NULLABLE en un
UNIQUE: en Postgres NULL != NULL → dos filas con branch_id=NULL NO chocarían. El refresh por eso
hace DELETE de la ventana + INSERT (no ON CONFLICT sobre columnas nullables); ver services/
refresh.py. El índice de cobertura (metric, metric_date, branch_id) sirve el rango+filtro del
plano de lectura.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class DashboardDailyMetric(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_daily_metric"
    __table_args__ = (
        UniqueConstraint(
            "metric_date",
            "branch_id",
            "metric",
            "segment",
            name="uq_dashboard_daily_metric_grain",
        ),
        Index(
            "ix_dashboard_daily_metric_lookup",
            "metric",
            "metric_date",
            "branch_id",
        ),
    )

    # Día del agregado (frontera UTC). El render local lo maneja el front.
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    # FK LÓGICA a clinic.branch (sin constraint, ADR-009). NULL = clínica entera.
    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # DashboardMetric value (code-level): conversations | leads_created | lead_stage | ...
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    # Desglose: status_code / lead_status_code / source / 'bot'. NULL = escalar.
    segment: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Conteo agregado.
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Valor monetario/numérico agregado (costo bot, ingreso). NULL = solo-conteo. Numeric(14,6)
    # para preservar costos LLM sub-centavo (cost_estimated_usd es Numeric(10,6)); el wire lo
    # formatea a 2 decimales (review F1). Serializa como STRING en el wire.
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
