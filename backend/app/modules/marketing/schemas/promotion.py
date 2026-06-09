"""
Schemas Pydantic v2 de Promotion.

Convenciones (idénticas a catalog/crm): sin Ellipsis; mensajes de validator en inglés;
`code` slug inmutable; `discount_type` INMUTABLE post-create (no va en Update). **El rango
discount_type↔discount_value NO se valida en Pydantic** — vive en el SERVICE
(`_validate_discount`), para que `update` (sin discount_type) lo imponga uniforme. Decimal
serializa como string en el wire.

Ciclo de imports: `PromotionOption` (leaf, sin deps de campaign) se define ANTES del
late-import de `CampaignOption`; el forward-ref `PromotionDetail.campaigns` se resuelve con
`model_rebuild()` al pie (mold `bots/schemas/bot_configuration.py`). Rompe el ciclo
bidireccional con `campaign.py` sin importar el orden de import.
"""

from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.product import ProductOption  # FK cross-módulo (read)
from app.modules.marketing.enums import DiscountType

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")  # ISO 4217


class PromotionOption(BaseModel):
    """Molde de ProductOption — trae el descuento listo para mostrar (selects, M:N de
    campaña). Leaf: NO depende de campaign (rompe el ciclo)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    discount_type: DiscountType
    discount_value: Decimal
    currency: str


class PromotionCreate(BaseModel):
    """El rango discount_type↔discount_value se valida en el SERVICE (no acá)."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    discount_type: DiscountType
    discount_value: Decimal = Field(max_digits=10, decimal_places=2)
    currency: str = "PEN"
    start_date: date_type
    end_date: date_type | None = None
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_person: int | None = Field(default=None, ge=1)
    applies_to_all_products: bool = False

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-40 chars)"
            )
        return v

    @field_validator("currency")
    @classmethod
    def _currency_iso(cls, v: str) -> str:
        if not CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be an ISO 4217 code (3 uppercase letters)")
        return v


class PromotionUpdate(BaseModel):
    """`code` y `discount_type` inmutables vía update (no se declaran)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    discount_value: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    currency: str | None = None
    start_date: date_type | None = None
    end_date: date_type | None = None
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_person: int | None = Field(default=None, ge=1)
    applies_to_all_products: bool | None = None
    active: bool | None = None

    @field_validator("currency")
    @classmethod
    def _currency_iso(cls, v: str | None) -> str | None:
        if v is not None and not CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be an ISO 4217 code (3 uppercase letters)")
        return v


class PromotionProductsReplace(BaseModel):
    """Body de PUT /promotions/{id}/products — bulk-replace del M:N de productos."""

    product_ids: list[str] = Field(default_factory=list)

    @field_validator("product_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("product_ids must not contain duplicates")
        return v


class PromotionItem(BaseModel):
    """Fila de la tabla. Denormaliza products_count/campaigns_count (NO en ALLOWED_FIELDS)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    discount_type: DiscountType
    discount_value: Decimal
    currency: str
    start_date: date_type
    end_date: date_type | None
    max_uses_total: int | None
    max_uses_per_person: int | None
    applies_to_all_products: bool
    products_count: int  # 0 si applies_to_all_products=true
    campaigns_count: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class PromotionDetail(PromotionItem):
    """Detalle: productos (vacío si applies_to_all_products), campañas (read-only), total_uses.

    ⚠ SUBSET F2: `total_uses` = 0 (PromotionUsage llega en F3; el cómputo real + el endpoint
    usage-summary se cablean en F3)."""

    products: list[ProductOption] = Field(default_factory=list)
    campaigns: list[CampaignOption] = Field(default_factory=list)  # forward-ref → model_rebuild
    total_uses: int = 0


# Late import + model_rebuild para romper el ciclo bidireccional con campaign.py (mold
# bots/schemas/bot_configuration). `PromotionOption` ya está definido arriba, así que el
# import de campaign.py puede resolverlo aunque entremos por cualquiera de los dos módulos.
from app.modules.marketing.schemas.campaign import CampaignOption  # noqa: E402

PromotionDetail.model_rebuild()
