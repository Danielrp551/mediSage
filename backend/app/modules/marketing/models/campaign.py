"""
Campaign = una campaña de marketing (un esfuerzo comercial con vigencia y, vía el
M:N `campaign_promotion`, un set de promociones). `code` es un slug estable en
minúsculas (patrón catalog.Vertical.code). `status` es CampaignStatus.value (varchar
plano, NO catálogo); las transiciones las valida el service contra la matriz
hardcodeada (ADR-013). `target_vertical_id` es FK REAL a catalog.vertical
(NULL = campaña transversal a todas las verticales). SIN relationship a Vertical
(se resuelve `target_vertical_name` por vertical_repository.get_by_ids batch).

⚠ SUBSET F1: el relationship `promotions` (M:N campaign_promotion ↔ Promotion) NO se
declara todavía — Promotion no existe hasta F2 y declararlo rompería el mapper al boot.
Llega en F2 (junto con `models/associations.py`); en F1 `promotions_count`=0 y
`CampaignDetail.promotions`=[].
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.marketing.enums import CampaignStatus
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Campaign(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "campaign"
    __table_args__ = (
        Index("ix_campaign_target_vertical", "target_vertical_id"),
        Index("ix_campaign_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # NULL = sin cierre conocido
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CampaignStatus.draft.value
    )
    # FK REAL a catalog.vertical (NULL = transversal). SIN relationship ORM.
    target_vertical_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vertical.id"), nullable=True
    )
