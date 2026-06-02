"""
El hilo cliente ACTUAL de una Person (ADR-003). El índice UNIQUE es PARCIAL
(`WHERE deleted_at IS NULL`) ⇒ a lo sumo UNA fila viva por persona. Al transicionar
a un estado `is_final` (ej. PERDIDO) la fila se SOFT-DELETEA (la traza queda en
customer_status_history; "reabrir" = fila nueva). Así, la existencia de una fila no
borrada ⟺ "es cliente". Una Person puede tener lead Y cliente a la vez (ADR-003).

`became_customer_at` se fija una sola vez (la primera promoción) y se conserva a
través de los cambios de estado; `entered_status_at` marca cuándo entró al estado
actual. SIN `source_campaign_id` (la atribución de campaña vive en el hilo lead).

El UNIQUE TOTAL (UniqueConstraint) NO sirve: bloquearía reabrir tras un cierre (la
fila soft-deleted seguiría ocupando el slot). Por eso es índice parcial, igual que
`person_lead_status` — dialect-agnóstico (`postgresql_where`+`sqlite_where`) para que
el smoke en sqlite también lo aplique. NO declaramos relationship a Person (se
consulta por person_id + batch maps; igual criterio que el hilo lead).
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


class PersonCustomerStatus(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "person_customer_status"
    __table_args__ = (
        Index(
            "uq_person_customer_status_person",
            "person_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    customer_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_status.id"), nullable=False
    )
    # Primera vez que se volvió cliente (se conserva a través de los cambios de estado).
    became_customer_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Cuándo entró al estado actual.
    entered_status_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
