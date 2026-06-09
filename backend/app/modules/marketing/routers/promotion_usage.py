"""
Validación / aplicación de promociones + reporte de usos. SIN prefix propio: los paths son
absolutos bajo `/marketing` (el aggregator). Agrupa por permiso: `/promotions/eligible-for`
y `/promotions/{id}/validate` + `/compute-price` son PROMOTION_VALIDATE; `/promotion-usages`
(crear redención) es PROMOTION_APPLY; `/promotion-usages/list` es PROMOTION_USAGES_READ.

⚠ `/promotions/eligible-for` (literal) se declara ANTES de `/promotions/{id}/validate`. Este
router se incluye DESPUÉS de `promotion.py` en el aggregator; los paths son inequívocos
(`eligible-for` literal no es un UUID; `/{id}/validate` es un segmento literal distinto de
`/{id}` / `/{id}/products` / `/{id}/usage-summary` de promotion.py).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.marketing.schemas.promotion_usage import (
    ApplyPromotionRequest,
    ComputePriceRequest,
    ComputePriceResponse,
    PromotionEligibility,
    PromotionEligibilityRequest,
    PromotionUsageDetail,
    PromotionUsageItem,
)
from app.modules.marketing.services import promotion_usage as usage_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(tags=["marketing · promotion usage"])  # sin prefix; paths absolutos

PromotionIdPath = Annotated[str, Path(min_length=1, description="Promotion UUID")]


@router.post(
    "/promotions/eligible-for",
    response_model=SingleResponse[list[PromotionEligibility]],
    dependencies=[Depends(RequirePermission("PROMOTION_VALIDATE"))],
)
async def eligible_for(
    payload: PromotionEligibilityRequest, db: DBSession
) -> SingleResponse[list[PromotionEligibility]]:
    return await usage_service.eligible_for(
        db, product_id=payload.product_id, person_id=payload.person_id
    )


@router.post(
    "/promotions/{promotion_id}/validate",
    response_model=SingleResponse[PromotionEligibility],
    dependencies=[Depends(RequirePermission("PROMOTION_VALIDATE"))],
)
async def validate_promotion(
    promotion_id: PromotionIdPath, payload: PromotionEligibilityRequest, db: DBSession
) -> SingleResponse[PromotionEligibility]:
    return await usage_service.validate(
        db,
        promotion_id=promotion_id,
        product_id=payload.product_id,
        person_id=payload.person_id,
    )


@router.post(
    "/compute-price",
    response_model=SingleResponse[ComputePriceResponse],
    dependencies=[Depends(RequirePermission("PROMOTION_VALIDATE"))],
)
async def compute_price(
    payload: ComputePriceRequest, db: DBSession
) -> SingleResponse[ComputePriceResponse]:
    return await usage_service.compute_price(
        db,
        product_id=payload.product_id,
        person_id=payload.person_id,
        promotion_id=payload.promotion_id,
    )


@router.post(
    "/promotion-usages",
    response_model=SingleResponse[PromotionUsageDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("PROMOTION_APPLY"))],
)
async def apply_promotion(
    payload: ApplyPromotionRequest, db: DBSession, actor: CurrentAuth
) -> SingleResponse[PromotionUsageDetail]:
    return await usage_service.apply(
        db,
        promotion_id=payload.promotion_id,
        person_id=payload.person_id,
        product_id=payload.product_id,
        appointment_id=payload.appointment_id,
        campaign_id=payload.campaign_id,
        notes=payload.notes,
        actor_id=actor.id,
    )


@router.post(
    "/promotion-usages/list",
    response_model=PaginatedResponse[PromotionUsageItem],
    dependencies=[Depends(RequirePermission("PROMOTION_USAGES_READ"))],
)
async def list_promotion_usages(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[PromotionUsageItem]:
    return await usage_service.list_paginated(db, query)
