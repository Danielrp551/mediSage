"""Routers de `marketing` (skeleton inerte en F0).

Por fase, sub-routers con su prefix interno bajo el aggregator `APIRouter(prefix=
"/marketing")`: F1 `campaign.py` (/campaigns + /campaigns/{id}/transition + M:N) ·
F2 `promotion.py` (/promotions + M:N + usage-summary) · F3 `promotion_usage.py`
(/promotions/eligible-for, /promotions/{id}/validate, /compute-price,
/promotion-usages[, /list]). PUT no PATCH. `RequirePermission` por endpoint.

⚠ F0: este paquete NO exporta un `router` ni se incluye en `app/main.py` → 0 rutas
montadas. F1 crea el aggregator y lo registra (`from app.modules.marketing.routers
import router as marketing_router`).
"""
