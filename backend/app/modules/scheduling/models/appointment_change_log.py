"""
Log inmutable de cambios in-place de columnas NO-estado de una cita (doctor_id,
office_id, notes, product_id, …). Sin SoftDeleteMixin (append-only). Los cambios de
status_id NO van acá (van a AppointmentStatusHistory); scheduled_for NO se edita
in-place (eso es /reschedule, que crea una cita nueva). previous_value/new_value se
serializan a texto (UUID/ISO8601/string) — un solo formato para cualquier columna.

La tabla se crea en F2 (migración 0021); el WRITER (update con changelog) llega en F3.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class AppointmentChangeLog(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "appointment_change_log"

    appointment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(60), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
