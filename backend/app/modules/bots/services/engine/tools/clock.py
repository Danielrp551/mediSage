"""
Tool de anclaje temporal del bot (sin BD): el LLM no conoce la fecha actual y "adivina"
años/días al interpretar fechas del usuario ("sábado 13" → año de su entrenamiento). La
práctica recomendada es grounding explícito vía tool dedicada en cada turno que maneje
fechas, no una fecha congelada en el system_prompt (las versiones de prompt son estáticas).
Devuelve fecha/hora/día de semana en la zona horaria del negocio (Settings.BOT_TIMEZONE),
con el weekday ya en español para que el modelo no lo traduzca/calcule.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool

_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


@register_tool("get_current_datetime")
async def get_current_datetime(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Fecha/hora actual en la TZ del negocio. Sin argumentos, sin BD: determinística
    y barata — el LLM debe llamarla antes de interpretar cualquier fecha."""
    tz_name = get_settings().BOT_TIMEZONE
    now = datetime.now(ZoneInfo(tz_name))
    return {
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M"),
        "weekday": _WEEKDAYS_ES[now.weekday()],
        "day": now.day,
        "month": _MONTHS_ES[now.month - 1],
        "year": now.year,
        "timezone": tz_name,
    }
