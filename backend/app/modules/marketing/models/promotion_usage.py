"""
PromotionUsage = el registro INMUTABLE de una redención de promoción (audit append-only;
PK·A·T, SIN SoftDeleteMixin). Snapshotea original/discount/final + currency al momento de
aplicar (no se recalcula nunca). created_on/created_by hacen de applied_at/applied_by (no
hay columnas separadas); aplicación automática (bot/scheduling F4) → created_by =
SYSTEM_USER_ID. NO stacking: UNIQUE PARCIAL sobre appointment_id WHERE appointment_id IS NOT
NULL (una promo por cita). Todas las FKs son REALES (las tablas existen) pero SIN
relationship ORM (acceso por id + batch maps, igual que appointment).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class PromotionUsage(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "promotion_usage"
    __table_args__ = (
        Index("ix_promotion_usage_promotion", "promotion_id"),
        Index("ix_promotion_usage_person", "person_id"),
        Index("ix_promotion_usage_product", "product_id"),
        Index("ix_promotion_usage_appointment", "appointment_id"),
        Index("ix_promotion_usage_campaign", "campaign_id"),
        Index("ix_promotion_usage_created_on", "created_on"),
        # NO stacking: una promo por cita. UNIQUE PARCIAL dialect-agnóstico (lección crm F1):
        # postgresql_where para prod, sqlite_where para el smoke. SIN cláusula deleted_at
        # (no hay SoftDelete en esta tabla).
        Index(
            "uq_promotion_usage_appointment",
            "appointment_id",
            unique=True,
            postgresql_where=text("appointment_id IS NOT NULL"),
            sqlite_where=text("appointment_id IS NOT NULL"),
        ),
    )

    promotion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("promotion.id"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("product.id"), nullable=False)
    # NULL = redención sin cita. FK REAL a scheduling.appointment.
    appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=True
    )
    # NULL = sin campaña asociada. FK REAL a campaign.
    campaign_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("campaign.id"), nullable=True
    )
    original_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # base_price
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # descontado
    final_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )  # original-discount
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # snapshot product.currency
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
