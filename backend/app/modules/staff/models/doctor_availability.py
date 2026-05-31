"""
DoctorAvailability = UN bloque concreto de disponibilidad de un doctor en una
fecha específica, en un `(branch, office)` específico (ADR-007). Reemplaza el
modelo Pattern+Override: NO hay day_of_week, NO hay recurrencia, NO hay flag
is_available. "No disponible" = no hay bloque; "vacaciones" = sin bloques;
"disponibilidad extra" = agregar un bloque.

`date` es una fecha de calendario (sin hora); `opens_at`/`closes_at` son `time`
naive (sin TZ) interpretados en `branch.timezone`. CHECK closes_at > opens_at:
un bloque nunca cruza medianoche (eso se modela como dos bloques en dos fechas).
Los cierres del consultorio viven en clinic.OfficeClosure — scheduling los resta;
staff no.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.staff.models.doctor import Doctor


class DoctorAvailability(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (
        CheckConstraint(
            "closes_at > opens_at",
            name="ck_doctor_availability_closes_after_opens",
        ),
    )

    doctor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("doctor.id"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(String(36), ForeignKey("branch.id"), nullable=False)
    office_id: Mapped[str] = mapped_column(String(36), ForeignKey("office.id"), nullable=False)
    # Fecha concreta; las horas locales se interpretan en branch.timezone.
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    closes_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)

    doctor: Mapped[Doctor] = relationship(back_populates="availability", lazy="raise")
