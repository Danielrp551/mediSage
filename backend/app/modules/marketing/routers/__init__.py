"""
Aggregator de los sub-routers de `marketing` bajo un solo prefix (`/marketing`).
`main.py` incluye este `router` una vez. El orden importa solo dentro de cada
sub-router (rutas estáticas — `/active` — antes de `/{id}`).

Por fase: F1 `campaign.py` (/campaigns + /campaigns/{id}/transition). F2 sumó
`promotion.py` (/promotions + M:N de productos) y el M:N de campañas. F3 suma el
`/{id}/usage-summary` en `promotion.py` + `promotion_usage.py` (/promotions/eligible-for,
/promotions/{id}/validate, /compute-price, /promotion-usages[, /list]). PUT no PATCH.
`RequirePermission` por endpoint. `promotion_usage_router` se incluye DESPUÉS de
`promotion_router`: ambos cuelgan de /promotions/... pero los paths son inequívocos.
"""

from fastapi import APIRouter

from app.modules.marketing.routers.campaign import router as campaign_router
from app.modules.marketing.routers.promotion import router as promotion_router
from app.modules.marketing.routers.promotion_usage import router as promotion_usage_router

router = APIRouter(prefix="/marketing")
router.include_router(campaign_router)  # /campaigns/* (+ /{id}/transition + M:N promociones)
router.include_router(promotion_router)  # /promotions/* (+ M:N productos + usage-summary)
router.include_router(promotion_usage_router)  # eligible-for / validate / compute-price / usages

__all__ = ["router"]
