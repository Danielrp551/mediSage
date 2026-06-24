from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DashboardFilter(BaseModel):
    """Body común de las 4 lecturas POST (+ del report en F3). branch_id None = clínica entera
    (las etapas previas a 'cita' SIEMPRE son a nivel clínica — solo appointment tiene branch_id).
    source/campaign_id = filtros opcionales (source filtra appointments_source / segment 'bot';
    campaign_id reservado para atribución de campaña vía lead_status_history.source_campaign_id).

    La validación de rango (date_to >= date_from, ≤ 366 días) vive en el SERVICE (metrics._guard_range
    → BadRequestException code=DASHBOARD_INVALID_DATE_RANGE, 400) y NO en un model_validator de
    Pydantic: el contrato (§8) exige el CODE de dominio (400), no un 422 de forma sin code (lección §22)."""

    date_from: date
    date_to: date
    branch_id: str | None = None
    source: str | None = None
    campaign_id: str | None = None
