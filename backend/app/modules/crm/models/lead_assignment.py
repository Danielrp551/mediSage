"""
El asesor que es OWNER del lead activo de una Person. UNIQUE PARCIAL sobre
`person_id` (`WHERE deleted_at IS NULL`) ⇒ a lo sumo un owner vivo. Reasignar =
soft-delete de la fila actual + insert nueva + LeadActivity(REASSIGNED), en UNA tx.
`advisor_user_id` SÍ es FK a user.id (admin.user ya existe). `assigned_by` es FK
lógica (string sin constraint): puede ser el SYSTEM user o NULL en round-robin auto.
Sin relationship a Person (se consulta por person_id + batch maps).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class LeadAssignment(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "lead_assignment"
    __table_args__ = (
        Index(
            "uq_lead_assignment_person",
            "person_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_lead_assignment_advisor", "advisor_user_id"),
    )

    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    advisor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # NULL=auto
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
