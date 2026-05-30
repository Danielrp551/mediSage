"""
Doctor = perfil profesional de un clínico, 1:1 con admin.User (ADR-002). El User
guarda identidad/auth (email, nombre, password, rol); Doctor guarda los datos
profesionales (colegiatura, bio, foto, firma, grano de slot) y los M:N hacia las
Sedes donde atiende y las Verticales que cubre.

`user_id` es UNIQUE e inmutable post-creación — mover un perfil a otra identidad
no es una operación soportada. `slot_duration_min` es la unidad mínima agendable
del calendario del doctor; scheduling redondea la duración del producto a un
múltiplo de él (ver ADR-006). El soft-delete de un Doctor NO toca al User
(ADR-002): para bloquear el acceso a la plataforma se pone `user.active = false`
desde el módulo admin.

La relación `availability` (1:N a DoctorAvailability) se agrega en la fase F2,
cuando exista ese modelo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.admin.models.user import User
    from app.modules.catalog.models.vertical import Vertical
    from app.modules.clinic.models.branch import Branch


class Doctor(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "doctor"

    # 1:1 con admin.User. UNIQUE impone la regla de un-perfil-por-usuario a nivel
    # de BD; inmutable post-creación (DoctorUpdate no lo declara).
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), unique=True, nullable=False, index=True
    )
    # Código del Colegio Médico del Perú (u homólogo). Nullable para no-médicos
    # (esteticistas, kinesiólogos). Indexado para reportes oficiales futuros.
    cmp_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Grano del calendario para scheduling. Default 30 min.
    slot_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # El User que este perfil extiende. `lazy="raise"` — se carga explícitamente
    # con selectinload cuando una vista de detalle/lista necesita full_name/email.
    user: Mapped[User] = relationship(lazy="raise")

    # M:N con clinic.Branch (sedes donde atiende). `lazy="raise"`: se carga con
    # selectinload + filtro deleted_at en el repositorio.
    branches: Mapped[list[Branch]] = relationship(secondary=doctor_branch, lazy="raise")
    # M:N con catalog.Vertical (verticales que cubre). Misma estrategia.
    verticals: Mapped[list[Vertical]] = relationship(secondary=doctor_vertical, lazy="raise")
