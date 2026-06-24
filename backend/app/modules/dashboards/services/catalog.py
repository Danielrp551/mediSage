"""
Resolución de catálogos de estado por CODE (ADR-008). NO hardcodea ids ni asume orden: lee
lead_status / appointment_status (catálogos en BD, configurables por admin) y expone los codes +
flags para que metrics.py componga el embudo/KPIs SIN ids mágicos. El code 'won' (CITA_AGENDADA)
se descubre por FLAG is_won (robusto a renombrados). Los sets de codes de etapa/cita son el ÚNICO
punto a tocar si la clínica reconfigura el embudo (no hay un flag "engaged"/"confirmada" en el
catálogo). Se resuelve por request (2 SELECT chicos; NO cache de proceso: admin edita sin redeploy).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.repositories.lead_status import lead_status_repository
from app.modules.scheduling.repositories.appointment_status import appointment_status_repository

# Etapa 3 del embudo (Contactados/Interesados). Codes del catálogo lead_status (seed crm F2).
ENGAGED_LEAD_CODES = {"CONTACTADO", "INTERESADO", "EVALUANDO"}
# Cita "confirmada o más avanzada" (el catálogo appointment_status NO tiene un flag is_confirmed;
# is_final cubre ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED y is_active_attention solo IN_PROGRESS →
# se enumeran los codes que cuentan como "llegó a confirmar"). Único punto a ajustar (ADR-008).
CONFIRMED_OR_BEYOND_APPT_CODES = {"CONFIRMED", "CHECKED_IN", "IN_PROGRESS", "ATTENDED"}
ATTENDED_APPT_CODE = "ATTENDED"
NO_SHOW_APPT_CODE = "NO_SHOW"
RESCHEDULED_APPT_CODE = "RESCHEDULED"  # cita hija del reagendamiento → excluir del 'agendadas'


async def lead_status_map(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """{code: {name, color, display_order, is_won, is_final}} de los estados de lead vivos."""
    statuses = await lead_status_repository.list_active(db)
    return {
        s.code: {
            "name": s.name,
            "color": s.color,
            "display_order": s.display_order,
            "is_won": s.is_won,
            "is_final": s.is_final,
        }
        for s in statuses
    }


async def appointment_status_map(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """{code: {name, color, display_order, is_final, is_active_attention}} de los estados de cita."""
    statuses = await appointment_status_repository.list_active(db)
    return {
        s.code: {
            "name": s.name,
            "color": s.color,
            "display_order": s.display_order,
            "is_final": s.is_final,
            "is_active_attention": s.is_active_attention,
        }
        for s in statuses
    }


def won_lead_code(lead_map: dict[str, dict[str, Any]]) -> str | None:
    """El code is_won (CITA_AGENDADA en el seed) descubierto por FLAG, no hardcodeado (ADR-008)."""
    for code, meta in lead_map.items():
        if meta["is_won"]:
            return code
    return None
