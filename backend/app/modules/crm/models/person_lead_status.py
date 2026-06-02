"""
El hilo lead ACTUAL de una Person (ADR-003). El índice UNIQUE es PARCIAL
(`WHERE deleted_at IS NULL`) ⇒ a lo sumo UNA fila viva por persona. Al transicionar
a un estado `is_final` la fila se SOFT-DELETEA (la traza queda en lead_status_history;
"reabrir" = fila nueva). Así, la existencia de una fila no borrada ⟺ "lead activo".

El UNIQUE TOTAL (UniqueConstraint) NO sirve: bloquearía reabrir tras un cierre (la
fila soft-deleted seguiría ocupando el slot). Por eso es índice parcial, igual que
`person_contact_identifier` — dialect-agnóstico (`postgresql_where`+`sqlite_where`)
para que el smoke en sqlite también lo aplique.

`source_campaign_id` es FK forward (ADR-009): varchar(36)+index, SIN ForeignKey ni
relationship — marketing agrega la constraint después. No declaramos relationship a
Person (se consulta por person_id + batch maps; igual criterio que los historiales).
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


class PersonLeadStatus(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "person_lead_status"
    __table_args__ = (
        Index(
            "uq_person_lead_status_person",
            "person_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_person_lead_status_campaign", "source_campaign_id"),
    )

    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False
    )
    # FK forward a marketing.campaign — varchar(36)+index, SIN FK/relationship (ADR-009).
    source_campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entered_status_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Denormalizado para el listado de personas (última actividad que tocó este lead).
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
