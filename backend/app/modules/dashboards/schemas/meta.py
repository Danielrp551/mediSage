from __future__ import annotations

from pydantic import BaseModel, Field


class StatusOption(BaseModel):
    """Un estado del catálogo (lead o appointment) para los colores del chart + leyenda."""

    code: str
    name: str
    color: str | None = None
    display_order: int


class BranchOption(BaseModel):
    """Una sede para el select de filtro."""

    id: str
    name: str


class DashboardMeta(BaseModel):
    """Respuesta de GET /meta. Alimenta los selects (sedes/orígenes) + los colores/labels de los
    charts (estados) + el badge 'Actualizado hace N min' (last_refreshed_at)."""

    last_refreshed_at: str | None = None  # ISO 8601 UTC; None antes del primer refresh
    lead_statuses: list[StatusOption] = Field(default_factory=list)
    appointment_statuses: list[StatusOption] = Field(default_factory=list)
    branches: list[BranchOption] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)  # AppointmentSource values
