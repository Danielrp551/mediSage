"""
Promotion = un descuento discriminado (percentage | fixed_amount). `discount_type` es
INMUTABLE post-create (no se cambia percentage↔fixed). `discount_value` es Decimal
Numeric(10,2): percentage 0<v≤100, fixed v>0 (validado en el SERVICE, no Pydantic, para
que update lo imponga uniforme). `currency` ISO 4217 (solo aplica si fixed_amount).
applies_to_all_products=true ignora el M:N promotion_product. SIN relationship a Product
(catalog, otro módulo) — el M:N promotion_product se resuelve por query propia.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.marketing.models.associations import campaign_promotion
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.marketing.models.campaign import Campaign


class Promotion(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "promotion"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    discount_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # DiscountType — INMUTABLE
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PEN"
    )  # ISO (solo fixed)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    max_uses_total: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = ilimitado
    max_uses_per_person: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # NULL = ilimitado
    applies_to_all_products: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Único relationship ORM cross-entidad del módulo (mismo módulo). lazy="raise":
    # se carga con selectinload() explícito en el repo/service cuando hace falta.
    campaigns: Mapped[list[Campaign]] = relationship(
        secondary=campaign_promotion, back_populates="promotions", lazy="raise"
    )
