"""Repositorios de `marketing` (skeleton inerte en F0).

Por fase: F1 `campaign.py` (CampaignRepository: get_by_code/list_active/get_by_ids/
campaign_name_map) · F2 `promotion.py` (PromotionRepository: + get_for_update para el
lock de max_uses) + `campaign_promotion.py` / `promotion_product.py` (M:N: set/count +
join propio a catalog.Product, SIN relationship en Product) · F3 `promotion_usage.py`
(get_by_appointment pre-check no-stacking + count_for_* + usage_summary). Cada repo
define su `ALLOWED_FIELDS` (solo columnas reales — lección cd10c78).
"""
