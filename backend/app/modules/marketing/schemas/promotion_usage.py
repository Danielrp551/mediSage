"""
Schemas Pydantic v2 de PromotionUsage (audit inmutable) + validación/precio.

PromotionUsageItem denormaliza promotion/person/product/campaign names + los montos
snapshot. SOLO 3 columnas de audit (sin updated_*): la entidad es PK·A·T sin SoftDelete
(spec §3.3). Apply/Eligibility/ComputePrice/Summary son los contratos del corazón de F3.
Decimal serializa como STRING en el wire (Numeric(10,2), lección base_price de catalog).
`PromotionOption` es leaf (no genera ciclo) — import directo seguro.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.marketing.schemas.promotion import PromotionOption


class PromotionUsageItem(BaseModel):
    """Fila del reporte de usos (read-only). Denormaliza los names + montos snapshot."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    promotion_id: str
    promotion_name: str  # denorm (promotion_name_map)
    person_id: str
    person_name: str  # denorm (crm.Person full_name vía person_option_map)
    product_id: str
    product_name: str  # denorm (catalog.Product.name)
    appointment_id: str | None
    campaign_id: str | None
    campaign_name: str | None  # denorm (NULL si campaign_id NULL o campaña inexistente)
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    currency: str
    notes: str | None
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None


class PromotionUsageDetail(PromotionUsageItem):
    """= Item; sin extras hoy (se tipa aparte por simetría con los demás módulos)."""


class ApplyPromotionRequest(BaseModel):
    """Body de POST /promotion-usages — crea un PromotionUsage (redención)."""

    promotion_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    appointment_id: str | None = None
    campaign_id: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class PromotionEligibilityRequest(BaseModel):
    """Body de POST /promotions/eligible-for — qué promos aplican a (product, person)."""

    product_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)


class PromotionEligibility(BaseModel):
    """Una promo evaluada para (product, person) — sin insertar nada."""

    promotion_id: str
    code: str
    name: str
    is_eligible: bool
    reason: str | None = None  # code del primer motivo de inelegibilidad (None si elegible)
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    currency: str


class ComputePriceRequest(BaseModel):
    """Body de POST /compute-price — precio final con/sin una promo puntual."""

    product_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    promotion_id: str | None = None


class ComputePriceResponse(BaseModel):
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    currency: str
    promotion: PromotionOption | None = None  # None si no se pidió promo


class PromotionUsageSummary(BaseModel):
    """Resumen de uso de una promo — GET /promotions/{id}/usage-summary."""

    promotion_id: str
    total_uses: int
    total_original_amount: Decimal
    total_discount_amount: Decimal
    total_final_amount: Decimal
