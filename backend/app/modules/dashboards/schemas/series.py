from __future__ import annotations

from pydantic import BaseModel, Field


class TimeSeriesPoint(BaseModel):
    """Un punto de la línea de evolución. `date` = ISO date (str). `values` = una clave por serie
    (por lead_status_code) → conteo de ese día. Las claves ausentes = 0 en el front."""

    date: str  # 'YYYY-MM-DD'
    values: dict[str, int] = Field(default_factory=dict)


class SeriesMeta(BaseModel):
    """Definición de una serie (para la leyenda + el color del chart)."""

    key: str  # lead_status_code
    label: str  # nombre del catálogo (ES)
    color: str | None = None  # lead_status.color


class TimeSeries(BaseModel):
    """Respuesta de POST /leads-evolution. series = las definiciones (leyenda/color); points = un
    punto por día del rango (bucketizado, días sin datos incluidos con values vacío)."""

    series: list[SeriesMeta]
    points: list[TimeSeriesPoint]
