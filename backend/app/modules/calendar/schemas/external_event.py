"""
Schemas del overlay informativo (Fase 2). `ExternalEventItem` = un evento externo leído
(detalle = título + horario, instantes UTC; el front los ubica en hora local del navegador).
`SourceHealth` = la salud por conexión tras el intento de lectura (best-effort §23: una
conexión que falla NO rompe la respuesta — viaja en sources_health con su code de error).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.calendar.enums import ConnectionStatus


class ExternalEventItem(BaseModel):
    """Un evento externo para el overlay. starts_at/ends_at UTC. branch_id/branch_name resuelven
    la sede del source (None = 'todas las sedes'). source_id ata el evento a su CalendarSource."""

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    branch_id: str | None = None
    branch_name: str | None = None
    source_id: str


class SourceHealth(BaseModel):
    """Salud de una conexión tras el intento de lectura (best-effort). error = code (None = OK)."""

    connection_id: str
    status: ConnectionStatus
    error: str | None = None


class ExternalEventsResponse(BaseModel):
    """Respuesta de GET /external-events. events = lo leído (de las conexiones que respondieron);
    sources_health = el estado por conexión (las que fallaron NO rompen la respuesta — la grilla
    muestra un aviso suave de salud)."""

    events: list[ExternalEventItem] = Field(default_factory=list)
    sources_health: list[SourceHealth] = Field(default_factory=list)
