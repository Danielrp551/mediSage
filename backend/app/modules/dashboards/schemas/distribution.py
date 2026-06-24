from __future__ import annotations

from pydantic import BaseModel


class DistributionBucket(BaseModel):
    """Una porción del donut. code = appointment_status_code; label/color del catálogo."""

    code: str
    label: str
    color: str | None = None
    count: int


class DistributionSummary(BaseModel):
    """Respuesta de POST /appointments-distribution. buckets = citas por estado (donut); total =
    suma (centro del donut). El donut muestra el estado ACTUAL (incluye RESCHEDULED) — no
    doble-cuenta porque cuenta filas por status_id, no transiciones."""

    buckets: list[DistributionBucket]
    total: int
