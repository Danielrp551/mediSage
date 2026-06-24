"""
Schemas Pydantic v2 del módulo `dashboards`. INERTE en F0.

F1 agrega (respuestas NO paginadas, molde marketing `usage_summary` → `SingleResponse[X]`):
`DashboardFilter` (request), `FunnelStage`/`FunnelSummary`, `TimeSeriesPoint`/`TimeSeries`,
`DistributionBucket`/`DistributionSummary`, `KpiSummary`, `DashboardMeta`, `RefreshResult`.
F3 agrega `ReportRequest` (+ `ReportFormat`). Las tasas se exponen como fracción 0–1; los montos
`Numeric` como string. Espejo en `frontend/src/types/dashboards.types.ts`.
"""
