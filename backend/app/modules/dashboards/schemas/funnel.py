from __future__ import annotations

from pydantic import BaseModel


class FunnelStage(BaseModel):
    """Una etapa del embudo (6). rate_from_prev = count_etapa / count_etapa_anterior (None en la
    1ª etapa); fracción 0..1 (el front formatea a %). color = del catálogo o token Fluent."""

    key: str  # 'conversations' | 'leads' | 'engaged' | 'appointments' | 'confirmed' | 'customers'
    label: str  # etiqueta ES ('Conversaciones', 'Leads', ...)
    count: int
    rate_from_prev: float | None = None
    color: str | None = None


class FunnelSummary(BaseModel):
    """Respuesta de POST /funnel. 6 etapas + las tasas agregadas (KPIs del embudo)."""

    stages: list[FunnelStage]
    conversion_rate: float  # lead_stage[code is_won] / leads_created (KPI HU26)
    total_leads: int
    total_appointments: int
    total_customers: int
    chatbot_share: float  # conversations[bot] / conversations (aporte del chatbot)
