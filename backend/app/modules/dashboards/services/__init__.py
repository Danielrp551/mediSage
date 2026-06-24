"""
Servicios (módulos de funciones, no clases) del módulo `dashboards`. INERTE en F0.

F1 agrega:
- `metrics`: compone `FunnelSummary`/`TimeSeries`/`DistributionSummary`/`KpiSummary`/`DashboardMeta`
  leyendo el rollup; resuelve los códigos/colores de estado desde los catálogos (ADR-008), NO los
  hardcodea.
- `refresh`: recomputa el rollup en la ventana móvil (idempotente, DELETE-de-ventana + INSERT) y
  actualiza `dashboard_refresh_state`. Lo dispara el Cloud Scheduler vía `/internal/refresh`.
F3 agrega `report`: genera PDF/Excel server-side (lazy import de reportlab/weasyprint + openpyxl).
"""
