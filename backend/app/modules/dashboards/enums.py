"""
Dashboards enums (code-level value sets, NO DB catalogs).

- DashboardMetric: el value de la columna `metric` del rollup `dashboard_daily_metric`. Cada
  miembro se materializa por día (× sede donde aplica, × segmento donde aplica) — ver §3 del
  backend.md / design.md §7. Los CODES de ESTADO (lead_status_code / appointment_status_code)
  que van en la columna `segment` NO se enuman aquí: son CATÁLOGOS configurables (ADR-008) → se
  resuelven por `code` desde lead_status / appointment_status (servicio `catalog`), nunca
  hardcodeados.

`ReportFormat` (pdf | excel) lo agrega F3 (reportes) en este mismo archivo.
"""

from __future__ import annotations

from enum import StrEnum


class DashboardMetric(StrEnum):
    conversations = "conversations"  # COUNT(DISTINCT person_id) conversation; segment 'bot' | NULL
    leads_created = "leads_created"  # COUNT(DISTINCT person_id) lead_status_history from=NULL
    lead_stage = (
        "lead_stage"  # COUNT(DISTINCT person_id) por to_lead_status_id (segment=lead_status_code)
    )
    appointments = "appointments"  # COUNT appointment por status_id (segment=appointment_status_code) + branch_id
    appointments_source = "appointments_source"  # COUNT appointment por source (segment=source)
    customers_new = "customers_new"  # COUNT(DISTINCT person_id) person_customer_status
    bot_turns = "bot_turns"  # COUNT bot_event WHERE event_type='turn_completed'
    bot_cost = "bot_cost"  # value=SUM(cost_estimated_usd); count=SUM(tokens_in+tokens_out)


class ReportFormat(StrEnum):
    """Formato del reporte exportable (F3). El request lo recibe como `str` (no este enum) para
    que un formato no soportado dé un 400 de dominio (REPORT_FORMAT_NOT_SUPPORTED) y no el 422 de
    Pydantic; el service `report` mapea el str a este enum (lección §22, igual que el rango)."""

    pdf = "pdf"
    excel = "excel"
