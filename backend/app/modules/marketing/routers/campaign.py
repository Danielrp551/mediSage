"""
Campaign CRUD + transición de estado. Permission gating vía `dependencies=[...]` en el
decorator; `actor: CurrentAuth` aparte cuando el handler necesita el id para audit.
`/active` (literal) se declara ANTES de `/{id}` (evita la captura de ruta).

El M:N de promociones (`GET`/`PUT /campaigns/{id}/promotions`) se cablea en F2 (bulk-replace).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.marketing.schemas.campaign import (
    CampaignCreate,
    CampaignDetail,
    CampaignItem,
    CampaignOption,
    CampaignPromotionsReplace,
    CampaignTransitionRequest,
    CampaignUpdate,
)
from app.modules.marketing.schemas.promotion import PromotionOption
from app.modules.marketing.services import campaign as campaign_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/campaigns", tags=["marketing · campaigns"])

CampaignIdPath = Annotated[str, Path(min_length=1, description="Campaign UUID")]


@router.get(
    "/active",
    response_model=list[CampaignOption],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))],
)
async def list_active_campaigns(db: DBSession) -> list[CampaignOption]:
    return await campaign_service.list_active(db)  # lista cruda, sin envelope


@router.post(
    "/list",
    response_model=PaginatedResponse[CampaignItem],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))],
)
async def list_campaigns(query: QueryRequest, db: DBSession) -> PaginatedResponse[CampaignItem]:
    return await campaign_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[CampaignDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("CAMPAIGNS_CREATE"))],
)
async def create_campaign(
    payload: CampaignCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[CampaignDetail]:
    return await campaign_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{campaign_id}",
    response_model=SingleResponse[CampaignDetail],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))],
)
async def get_campaign(
    campaign_id: CampaignIdPath, db: DBSession
) -> SingleResponse[CampaignDetail]:
    return await campaign_service.get_by_id(db, campaign_id)


@router.put(
    "/{campaign_id}",
    response_model=SingleResponse[CampaignDetail],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_UPDATE"))],
)
async def update_campaign(
    campaign_id: CampaignIdPath,
    payload: CampaignUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[CampaignDetail]:
    return await campaign_service.update(db, campaign_id, payload, actor_id=actor.id)


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("CAMPAIGNS_DELETE"))],
)
async def delete_campaign(campaign_id: CampaignIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await campaign_service.remove(db, campaign_id, actor_id=actor.id)


@router.post(
    "/{campaign_id}/transition",
    response_model=SingleResponse[CampaignDetail],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_UPDATE"))],
)
async def transition_campaign(
    campaign_id: CampaignIdPath,
    payload: CampaignTransitionRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[CampaignDetail]:
    return await campaign_service.transition(db, campaign_id, payload.to_status, actor_id=actor.id)


@router.get(
    "/{campaign_id}/promotions",
    response_model=SingleResponse[list[PromotionOption]],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))],
)
async def get_campaign_promotions(
    campaign_id: CampaignIdPath, db: DBSession
) -> SingleResponse[list[PromotionOption]]:
    return await campaign_service.get_promotions(db, campaign_id)


@router.put(
    "/{campaign_id}/promotions",
    response_model=SingleResponse[CampaignDetail],
    dependencies=[Depends(RequirePermission("CAMPAIGNS_UPDATE"))],
)
async def set_campaign_promotions(
    campaign_id: CampaignIdPath,
    payload: CampaignPromotionsReplace,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[CampaignDetail]:
    return await campaign_service.set_promotions(
        db, campaign_id, payload.promotion_ids, actor_id=actor.id
    )
