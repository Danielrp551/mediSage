"""
ADR-008: una arista configurable del grafo de estados de cliente (from → to).
Análoga a LeadStatusTransition (FKs a customer_status). SIN SoftDeleteMixin: es
config (active toggle / DELETE real). Seed permisivo (§Matriz base).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class CustomerStatusTransition(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "customer_status_transition"
    __table_args__ = (
        UniqueConstraint(
            "from_customer_status_id",
            "to_customer_status_id",
            name="uq_customer_status_transition_from_to",
        ),
    )

    from_customer_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_status.id"), nullable=False, index=True
    )
    to_customer_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_status.id"), nullable=False
    )
