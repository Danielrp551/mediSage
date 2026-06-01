"""
ADR-008: una arista configurable del grafo de estados de lead (from → to). El
service de transición (F3) la consulta para validar los cambios de estado. Editable
por admin (LEAD_STATUSES_WRITE): el seed instala una matriz base que la clínica
luego refina. SIN SoftDeleteMixin — es config: deshabilitar una arista = active=false
(conserva la fila) o DELETE real (la matriz no tiene historial).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class LeadStatusTransition(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "lead_status_transition"
    __table_args__ = (
        UniqueConstraint(
            "from_lead_status_id",
            "to_lead_status_id",
            name="uq_lead_status_transition_from_to",
        ),
    )

    from_lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False, index=True
    )
    to_lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False
    )
