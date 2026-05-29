"""
Product = a concrete sellable item inside a Service (e.g. "HydraFacial
Premium 60 min" under "Limpieza profunda"). The `code` slug is stable per
service and used by bots/reports — never renamed once issued.

`(service_id, code)` is unique within a service. The hierarchy is strict
`Vertical -> Service -> Product`; `service_id` is immutable after creation
(moving a product between services would orphan appointments/promotions that
reference it).

Booking-related columns (`duration_min`, `requires_appointment`,
`min_hours_to_cancel`) feed the scheduling module. `base_price` is stored as
NUMERIC(10,2) and serialised to the wire as a string to avoid float drift.

`vertical_id` is denormalized (a FK copied from the parent service on
create). It is immutable — `service_id` is immutable and a service's
`vertical_id` is immutable — so it never drifts. It exists so the catalog UI
can filter products by vertical through the standard `ALLOWED_FIELDS` path
without a join; `vertical_name` stays derived (it can be renamed).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.service import Service


class Product(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("service_id", "code", name="uq_product_service_code"),)

    service_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service.id"), nullable=False, index=True
    )
    # Denormalized parent vertical (see module docstring). FK column without a
    # relationship — the canonical path is product -> service -> vertical.
    vertical_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vertical.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PEN")
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_appointment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_package: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_hours_to_cancel: Mapped[int | None] = mapped_column(Integer, nullable=True)

    service: Mapped[Service] = relationship(back_populates="products", lazy="raise")
