"""
Schemas Pydantic v2 de Campaign.

Convenciones (idénticas a catalog/crm): sin Ellipsis en Field; mensajes de validator
en inglés (van al 422); `code` slug minúsculas inmutable post-create; `status` se
cambia SOLO vía /transition (no en Update). `target_vertical_name` y `promotions_count`
son denormalizados (NO van en ALLOWED_FIELDS — lección cd10c78).

⚠ SUBSET F1: `CampaignDetail.promotions` se declara (`list[PromotionOption]`) pero el
service devuelve `[]` y `promotions_count`=0 (el M:N llega en F2).
"""

from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption  # FK cross-módulo (read)
from app.modules.marketing.enums import CampaignStatus
from app.modules.marketing.schemas.promotion import PromotionOption

# Slug en minúsculas/dígitos/guion_bajo (patrón catalog.Vertical.code). Inmutable post-create.
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")


class CampaignOption(BaseModel):
    """Dropdown / M:N / atribución — id/code/name/status."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    status: CampaignStatus


class CampaignCreate(BaseModel):
    """status NO va (nace draft). target_vertical_id opcional (NULL = transversal)."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    start_date: date_type
    end_date: date_type | None = None
    target_vertical_id: str | None = None

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-40 chars)"
            )
        return v


class CampaignUpdate(BaseModel):
    """`code` y `status` inmutables vía update (status se cambia por /transition)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    start_date: date_type | None = None
    end_date: date_type | None = None
    target_vertical_id: str | None = None
    active: bool | None = None


class CampaignTransitionRequest(BaseModel):
    """Body de POST /campaigns/{id}/transition (valida la matriz hardcodeada)."""

    to_status: CampaignStatus


class CampaignPromotionsReplace(BaseModel):
    """Body de PUT /campaigns/{id}/promotions — bulk-replace del M:N (se cablea en F2)."""

    promotion_ids: list[str] = Field(default_factory=list)

    @field_validator("promotion_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("promotion_ids must not contain duplicates")
        return v


class CampaignItem(BaseModel):
    """Fila de la tabla de campañas. Denormaliza target_vertical_name + promotions_count
    (NINGUNO va en ALLOWED_FIELDS — lección cd10c78)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    start_date: date_type
    end_date: date_type | None
    status: CampaignStatus
    target_vertical_id: str | None
    target_vertical_name: str | None = None  # denorm de catalog.Vertical.name
    promotions_count: int  # 0 en F1 (sin M:N todavía)
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class CampaignDetail(CampaignItem):
    """Detalle: agrega la vertical resuelta + las promos del M:N (read-only en el
    detalle; se editan por PUT /campaigns/{id}/promotions). En F1 promotions = []."""

    target_vertical: VerticalOption | None = None
    promotions: list[PromotionOption] = Field(default_factory=list)
