"""
DashboardRefreshState = singleton de observabilidad del refresh. UNA fila (el service la crea
on-first-run y la actualiza in-place). NO es crítica para los datos del rollup; es para la UX
("Actualizado hace N min" en el panel y en el `meta`) y el diagnóstico del job. PK·A·T, SIN
SoftDelete. status ∈ {ok, running, error}.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class DashboardRefreshState(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_refresh_state"

    # Último refresh OK (para "Actualizado hace N min"). NULL antes del primer run.
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Ventana (días) recomputada en el último ciclo.
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ok | running | error.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ok")
    # Último error del job (observabilidad; NO bloquea las lecturas).
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
