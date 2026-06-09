"""Modelos SQLAlchemy de `marketing`.

Importarlos acá los registra en `Base.metadata` antes de que Alembic lea el esquema y
antes de resolver los relationship() por string. Orden: associations + campaign +
promotion (el M:N Campaign.promotions ↔ Promotion.campaigns necesita ambas tablas).

Por fase: F1 `campaign.py` (Campaign) · F2 `promotion.py` (Promotion) +
`associations.py` (campaign_promotion, promotion_product) · F3 `promotion_usage.py`
(PromotionUsage, PK·A·T sin SoftDelete). Mixins del template. PKs/FKs String(36).

⚠ SUBSET F2: aún NO se importa `PromotionUsage` (llega en F3).
"""

from app.modules.marketing.models.associations import (  # noqa: F401
    campaign_promotion,
    promotion_product,
)
from app.modules.marketing.models.campaign import Campaign
from app.modules.marketing.models.promotion import Promotion

__all__ = ["Campaign", "Promotion", "campaign_promotion", "promotion_product"]
