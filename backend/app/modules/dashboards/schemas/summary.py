from __future__ import annotations

from pydantic import BaseModel


class KpiSummary(BaseModel):
    """Respuesta de POST /summary. Tasas (float, 0..1 — el front formatea a %) + escalares (int)
    + el costo del bot (str: Numeric serializa como string). Fórmulas en design.md §7 / metrics.py
    (0.0 si el denominador es 0)."""

    # Tasas derivadas (fracción 0..1).
    conversion_rate: float  # lead_stage[is_won] / leads_created
    lead_to_appt_rate: float  # appointments(agendadas) / leads_created
    confirmation_rate: float  # appointments[confirmadas o más] / appointments(agendadas)
    show_rate: float  # appointments[ATTENDED] / (ATTENDED + NO_SHOW)
    no_show_rate: float  # appointments[NO_SHOW] / (ATTENDED + NO_SHOW)
    customer_rate: float  # customers_new / appointments[ATTENDED]
    # Escalares.
    total_conversations: int
    conversations_bot: int
    total_leads: int
    total_appointments: int
    total_confirmed: int
    total_attended: int
    total_customers: int
    bot_turns: int
    # Numeric → STRING en el wire (regla del template).
    bot_cost_usd: str
