"""
Schemas Pydantic v2 de Promotion.

⚠ SUBSET F1: en F1 solo se declara `PromotionOption` (un schema HOJA que NO depende
del modelo Promotion ni de catalog) porque `CampaignDetail.promotions` lo necesita
para tipar la lista (que en F1 siempre se serializa `[]`). El resto de los schemas de
Promotion (Create/Update/Item/Detail/ProductsReplace, que SÍ importan ProductOption y
CampaignOption) llega en F2. Mantener `PromotionOption` arriba evita el import circular
con `campaign.py` (promotion → enums; campaign → promotion).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.modules.marketing.enums import DiscountType


class PromotionOption(BaseModel):
    """Molde de ProductOption — trae el descuento listo para mostrar (selects, M:N de
    campaña). Decimal serializa como string en el wire."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    discount_type: DiscountType
    discount_value: Decimal
    currency: str
