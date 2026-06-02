"""
Log inmutable de transiciones del hilo cliente de una Person. SIN SoftDeleteMixin
(audit trail honesto). `from_customer_status_id` es NULL en la primera fila (la
promoción a cliente). `changed_by` es FK lógica a user.id (NULL/SYSTEM cuando es
automático). Análogo a `lead_status_history` PERO sin `source_campaign_id` (la
atribución de campaña es del hilo lead). NO declaramos relationship a Person.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class CustomerStatusHistory(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "customer_status_history"

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    from_customer_status_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("customer_status.id"), nullable=True
    )
    to_customer_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_status.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # FK lógica
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
