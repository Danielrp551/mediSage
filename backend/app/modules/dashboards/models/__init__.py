"""
Modelos del módulo `dashboards`. INERTE en F0 (sin tablas).

F1 agrega la capa de agregación materializada (ADR-015):
- `DashboardDailyMetric` (`dashboard_daily_metric`): rollup diario
  `metric_date x branch_id x metric x segment -> count/value`. UNIQUE(metric_date, branch_id,
  metric, segment) + índice (metric, metric_date, branch_id). Mixins PK·A·T (sin SoftDelete).
- `DashboardRefreshState` (`dashboard_refresh_state`): singleton de observabilidad del job de
  refresco (last_refreshed_at, window_days, status, last_error).

NO son entidades de negocio (son derivadas; el refresco las repuebla por DELETE-de-ventana + INSERT).
Migración `0026_dashboard_metric` + índices aditivos en las tablas fuente (lead_status_history.
changed_at, conversation.opened_at, person_customer_status.became_customer_at).
"""
