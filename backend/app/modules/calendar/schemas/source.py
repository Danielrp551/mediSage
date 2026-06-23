"""
Schemas de `CalendarSource` (el mapeo calendario→sede) + el body del bulk-replace +
la opción de calendario externo (de `list_calendars`, para el dropdown de mapeo).

`is_enabled` mapea `ActiveMixin.active` (flag de lectura, NO 2ª columna). `branch_name`
es denorm de clinic.Branch.name (None si branch_id NULL = "todas las sedes").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CalendarSourceItem(BaseModel):
    """Una fila de mapeo calendario→sede. branch_name denorm (NULL = 'Todas las sedes').
    is_enabled = ActiveMixin.active (flag de lectura, NO 2ª columna)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    connection_id: str
    external_calendar_id: str
    external_calendar_name: str
    branch_id: str | None = None
    branch_name: str | None = None  # denorm de clinic.Branch.name (None si branch_id NULL)
    is_enabled: bool  # mapea active


class CalendarSourceCreate(BaseModel):
    """Un mapeo en el body del bulk-replace. branch_id None = 'todas las sedes'."""

    external_calendar_id: str = Field(min_length=1, max_length=255)
    external_calendar_name: str = Field(min_length=1, max_length=255)
    branch_id: str | None = None
    is_enabled: bool = True


class CalendarSourcesReplace(BaseModel):
    """Body de PUT /connections/{id}/sources — REEMPLAZA el set completo de sources
    (patrón clinic.OfficeOperatingHours bulk-replace). min 0 (vaciar el mapeo es válido)."""

    sources: list[CalendarSourceCreate] = Field(default_factory=list)


class ExternalCalendarOption(BaseModel):
    """De list_calendars (live) — el dropdown de mapeo. NO se persiste (es del provider)."""

    id: str
    name: str
    primary: bool = False
