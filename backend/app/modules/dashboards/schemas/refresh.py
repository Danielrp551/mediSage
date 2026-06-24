from __future__ import annotations

from pydantic import BaseModel


class RefreshResult(BaseModel):
    """Respuesta de POST /internal/refresh (target Cloud Scheduler). Observabilidad del job."""

    refreshed_at: str  # ISO 8601 UTC del refresh recién hecho
    window_days: int
    rows_written: int  # filas del rollup escritas
    status: str  # 'ok' | 'error'
