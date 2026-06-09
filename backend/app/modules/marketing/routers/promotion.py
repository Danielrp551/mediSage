"""
Promotion CRUD + M:N de productos. `/active` (literal) ANTES de `/{id}`. PUT no PATCH;
el M:N de productos es bulk-replace por PUT. `actor: CurrentAuth` para las audit columns.

⚠ SUBSET F2: `GET /{id}/usage-summary` (y el cómputo de total_uses) llega en F3 (depende de
la tabla promotion_usage). El tab Campañas del detalle es read-only (se edita desde Campaña).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.catalog.schemas.product import ProductOption
from app.modules.marketing.schemas.promotion import (
    PromotionCreate,
    PromotionDetail,
    PromotionItem,
    PromotionOption,
    PromotionProductsReplace,
    PromotionUpdate,
)
from app.modules.marketing.services import promotion as promotion_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/promotions", tags=["marketing · promotions"])

PromotionIdPath = Annotated[str, Path(min_length=1, description="Promotion UUID")]


@router.get(
    "/active",
    response_model=list[PromotionOption],
    dependencies=[Depends(RequirePermission("PROMOTIONS_READ"))],
)
async def list_active_promotions(db: DBSession) -> list[PromotionOption]:
    return await promotion_service.list_active(db)  # lista cruda, sin envelope


@router.post(
    "/list",
    response_model=PaginatedResponse[PromotionItem],
    dependencies=[Depends(RequirePermission("PROMOTIONS_READ"))],
)
async def list_promotions(query: QueryRequest, db: DBSession) -> PaginatedResponse[PromotionItem]:
    return await promotion_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[PromotionDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("PROMOTIONS_CREATE"))],
)
async def create_promotion(
    payload: PromotionCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[PromotionDetail]:
    return await promotion_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{promotion_id}",
    response_model=SingleResponse[PromotionDetail],
    dependencies=[Depends(RequirePermission("PROMOTIONS_READ"))],
)
async def get_promotion(
    promotion_id: PromotionIdPath, db: DBSession
) -> SingleResponse[PromotionDetail]:
    return await promotion_service.get_by_id(db, promotion_id)


@router.put(
    "/{promotion_id}",
    response_model=SingleResponse[PromotionDetail],
    dependencies=[Depends(RequirePermission("PROMOTIONS_UPDATE"))],
)
async def update_promotion(
    promotion_id: PromotionIdPath,
    payload: PromotionUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PromotionDetail]:
    return await promotion_service.update(db, promotion_id, payload, actor_id=actor.id)


@router.delete(
    "/{promotion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("PROMOTIONS_DELETE"))],
)
async def delete_promotion(
    promotion_id: PromotionIdPath, db: DBSession, actor: CurrentAuth
) -> None:
    await promotion_service.remove(db, promotion_id, actor_id=actor.id)


@router.get(
    "/{promotion_id}/products",
    response_model=SingleResponse[list[ProductOption]],
    dependencies=[Depends(RequirePermission("PROMOTIONS_READ"))],
)
async def get_promotion_products(
    promotion_id: PromotionIdPath, db: DBSession
) -> SingleResponse[list[ProductOption]]:
    return await promotion_service.get_products(db, promotion_id)


@router.put(
    "/{promotion_id}/products",
    response_model=SingleResponse[PromotionDetail],
    dependencies=[Depends(RequirePermission("PROMOTIONS_UPDATE"))],
)
async def set_promotion_products(
    promotion_id: PromotionIdPath,
    payload: PromotionProductsReplace,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PromotionDetail]:
    return await promotion_service.set_products(
        db, promotion_id, payload.product_ids, actor_id=actor.id
    )
