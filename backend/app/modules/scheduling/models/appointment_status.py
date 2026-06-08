"""
AppointmentStatus — catálogo configurable de estados de cita (ADR-008). En BD para
que admin renombre / agregue estados sin deploy (espeja crm.LeadStatus). `code` en
MAYÚSCULAS, inmutable (los shortcuts del service de F3 resuelven por code —
`get_by_code("CONFIRMED")` —, así que renombrarlo los rompería). Banderas que
manejan el ciclo de vida sin hardcodear codes:
- is_initial: EXACTAMENTE uno true por catálogo (la cita nace aquí al agendar).
  Validado en el service (MULTIPLE_INITIAL_STATUS).
- is_final: estado terminal (ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED). NO soft-deletea
  la fila Appointment (registro histórico — diverge de crm, ver Appointment en F2).
- is_active_attention: 0..N (en la práctica solo IN_PROGRESS). Marca "en atención
  ahora" para la grilla y los reportes; NO se valida unicidad.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class AppointmentStatus(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "appointment_status"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # hex para badges
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
