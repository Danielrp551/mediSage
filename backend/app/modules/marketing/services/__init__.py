"""Services de `marketing` (módulos de funciones, no clases; skeleton inerte en F0).

Por fase: F1 `campaign.py` (CRUD + transition validando la matriz hardcodeada §2 +
set_promotions) · F2 `promotion.py` (CRUD + _validate_discount en service +
set_products + usage_summary) · F3 `promotion_usage.py` (apply en 10 pasos +
_compute_discount Decimal ROUND_HALF_UP cap + eligible_for/validate/compute_price).
Lanzan excepciones de dominio (nunca HTTPException); no hacen commit (get_db lo hace).
`apply` es atómico cuando lo invoca scheduling.create_appointment (F4, ADR-013 D2).
"""
