"""
Bitácora inmutable de transiciones del hilo lead de una Person. SIN SoftDeleteMixin
(audit trail honesto: no se borra ni soft-deletea). `from_lead_status_id` es NULL en
la primera fila (creación del lead). `changed_by` es FK lógica a user.id (NULL/SYSTEM
si automático). `source_campaign_id` es FK forward (ADR-009) — solo se llena al crear.
Sin relationship a Person (se consulta por person_id).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class LeadStatusHistory(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "lead_status_history"

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    from_lead_status_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=True
    )
    to_lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False
    )
    # FK forward a marketing.campaign — SIN FK constraint/relationship (ADR-009).
    source_campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # FK lógica a user
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
