"""
Log inmutable de transiciones de estado de una cita (espeja crm.LeadStatusHistory).
Sin SoftDeleteMixin (audit trail honesto, append-only). from_status_id es NULL en la
primera fila (creación de la cita). changed_by es FK a user.id (NULL = bot/sistema).
SIN relationship al padre (acceso por appointment_id + batch maps).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class AppointmentStatusHistory(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "appointment_status_history"

    appointment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=False, index=True
    )
    from_status_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=True
    )
    to_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
