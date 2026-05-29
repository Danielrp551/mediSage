"""
Service = a sellable line of work inside a Vertical (e.g. "Limpieza
profunda" under "Estética facial"). The `code` slug is stable per vertical
and used by bots/reports — never renamed once issued.

`(vertical_id, code)` is unique: the same slug can repeat across different
verticals but not within one. The hierarchy is strict
`Vertical -> Service -> Product`; `vertical_id` is immutable after creation
(moving a service between verticals would orphan its products).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.product import Product
    from app.modules.catalog.models.vertical import Vertical


class Service(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "service"
    __table_args__ = (UniqueConstraint("vertical_id", "code", name="uq_service_vertical_code"),)

    vertical_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vertical.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    vertical: Mapped[Vertical] = relationship(back_populates="services", lazy="raise")
    # Children. `lazy="raise"` keeps accidental N+1 loud — products_count is
    # computed with explicit batch queries in the service layer, not via this.
    products: Mapped[list[Product]] = relationship(back_populates="service", lazy="raise")
