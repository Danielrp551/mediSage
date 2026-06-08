"""
Appointment = la unidad persistida del calendario (ADR-006: la disponibilidad NO se
persiste, se calcula al vuelo; lo único que ocupa tiempo es esta fila). Reserva el
rango [scheduled_for, scheduled_for + duration_min) para el chequeo de conflicto.

`branch_id` es DENORM de office.branch_id (copiado al agendar — un office no se mueve
de sede). Habilita el índice (branch_id, scheduled_for, status_id) sin join.
`duration_min` se COPIA de product.duration_min al agendar (fallback
doctor.slot_duration_min si NULL); es exacto, no se redondea.

`previous_appointment_id` es self-FK (cadena de reagendamiento, acíclica por
construcción — la NUEVA apunta a la vieja). TODAS las FK cross-módulo son reales (las
tablas existen) pero SIN relationship ORM — se resuelven por id + batch maps (igual
que crm con status/advisor).

NO se soft-deletea al cerrar: una cita ATTENDED/CANCELLED/… mantiene la fila viva
(histórico). DELETE (soft) = solo error de captura. (Diverge de crm.)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Appointment(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "appointment"
    __table_args__ = (
        Index("ix_appointment_doctor_scheduled", "doctor_id", "scheduled_for"),
        Index("ix_appointment_office_scheduled", "office_id", "scheduled_for"),
        Index("ix_appointment_person_scheduled", "person_id", "scheduled_for"),
        Index(
            "ix_appointment_branch_scheduled_status",
            "branch_id",
            "scheduled_for",
            "status_id",
        ),
    )

    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    doctor_id: Mapped[str] = mapped_column(String(36), ForeignKey("doctor.id"), nullable=False)
    office_id: Mapped[str] = mapped_column(String(36), ForeignKey("office.id"), nullable=False)
    # DENORM de office.branch_id (copiado al agendar; el office no se mueve de sede).
    branch_id: Mapped[str] = mapped_column(String(36), ForeignKey("branch.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("product.id"), nullable=False)
    # Inicio de la cita, en UTC (timestamptz). El render local lo hace el browser.
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Copiado de product.duration_min al agendar (fallback doctor.slot_duration_min).
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=False
    )
    # AppointmentSource value (bot|advisor|admin|import|api).
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # Self-FK: la cita NUEVA guarda el id de la vieja. Acíclica por construcción.
    previous_appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
