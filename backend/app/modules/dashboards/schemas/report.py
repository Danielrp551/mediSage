"""
Request del reporte exportable (F3). Hereda `DashboardFilter` → reusa la validación de rango del
service (metrics._guard_range → DASHBOARD_INVALID_DATE_RANGE, 400) y el body común (date_from,
date_to, branch_id, source, campaign_id).

`format` se tipa `str` A PROPÓSITO (no el enum `ReportFormat`): el contrato (§8) exige que un
formato no soportado dé un 400 de DOMINIO (`REPORT_FORMAT_NOT_SUPPORTED`) y no el 422 de forma de
Pydantic — el service `report` mapea el str al enum y lanza el code de dominio (misma decisión que
el rango de fechas, lección §22). `sections` vacío = TODAS las secciones.
"""

from __future__ import annotations

from pydantic import Field

from app.modules.dashboards.schemas.filter import DashboardFilter


class ReportRequest(DashboardFilter):
    # "pdf" | "excel" — validado en el service (REPORT_FORMAT_NOT_SUPPORTED si no es uno de esos).
    format: str
    # subconjunto de "kpis" | "funnel" | "distribution" | "evolution"; vacío = todas.
    sections: list[str] = Field(default_factory=list)
