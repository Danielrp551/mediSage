"""
Modelos del módulo `dashboards` (F1). Importarlos acá los registra en Base.metadata antes de que
Alembic lea el esquema y antes del create_all del smoke. Sin orden de dependencia entre ellos (no
hay FK entre las 2 tablas; ambas son derivadas del rollup, PK·A·T sin SoftDelete — ADR-015).
"""

from app.modules.dashboards.models.dashboard_daily_metric import DashboardDailyMetric
from app.modules.dashboards.models.dashboard_refresh_state import DashboardRefreshState

__all__ = ["DashboardDailyMetric", "DashboardRefreshState"]
