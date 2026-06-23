"""
CalendarSource = un calendario concreto de una conexión, mapeado a una sede (Branch).
El conjunto de sources con is_enabled=true (active=true) ES "el grupo de calendarios
de la clínica" (resuelve la Q1 del design: una conexión global + N sources por sede).

`branch_id` NULLABLE = "todas las sedes" (decisión LOCKED #3). FK a clinic.branch con
ondelete RESTRICT (backstop hard-delete: no se puede borrar una sede con sources vivos).
`is_enabled` (flag de lectura) = ActiveMixin.active expuesto en el schema (NO 2ª columna).

UNIQUE PARCIAL (connection_id, external_calendar_id) WHERE deleted_at IS NULL: un mismo
calendario externo no se mapea dos veces vivo en la misma conexión; el bulk-replace
soft-deletea los viejos antes de insertar el set nuevo, así el par se libera.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.calendar.models.calendar_connection import CalendarConnection


class CalendarSource(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "calendar_source"
    __table_args__ = (
        Index(
            "uq_calendar_source_connection_external",
            "connection_id",
            "external_calendar_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_calendar_source_branch", "branch_id"),
    )

    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("calendar_connection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Id del calendario en el proveedor.
    external_calendar_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Denorm del nombre del calendario (para mostrar sin re-llamar al provider).
    external_calendar_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK cross-módulo a clinic.branch. NULLABLE = "todas las sedes". RESTRICT: la tabla
    # branch existe en prod (ADR-009 NO aplica) → FK real; sin relationship ORM cross-módulo.
    branch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("branch.id", ondelete="RESTRICT"), nullable=True
    )

    connection: Mapped[CalendarConnection] = relationship(back_populates="sources", lazy="raise")
