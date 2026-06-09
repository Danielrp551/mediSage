"""
Aggregator de los sub-routers de `marketing` bajo un solo prefix (`/marketing`).
`main.py` incluye este `router` una vez. El orden importa solo dentro de cada
sub-router (rutas estáticas — `/active` — antes de `/{id}`).

Por fase: F1 `campaign.py` (/campaigns + /campaigns/{id}/transition). F2 sumará
`promotion.py` (/promotions + M:N + usage-summary) y el M:N de campañas; F3
`promotion_usage.py` (/promotions/eligible-for, /promotions/{id}/validate,
/compute-price, /promotion-usages[, /list]). PUT no PATCH. `RequirePermission`
por endpoint.
"""

from fastapi import APIRouter

from app.modules.marketing.routers.campaign import router as campaign_router

router = APIRouter(prefix="/marketing")
router.include_router(campaign_router)  # /campaigns/* (+ /{id}/transition)

__all__ = ["router"]
