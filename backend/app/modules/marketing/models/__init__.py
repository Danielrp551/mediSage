"""Modelos SQLAlchemy de `marketing` (skeleton inerte en F0).

Por fase: F1 `campaign.py` (Campaign) · F2 `promotion.py` (Promotion) +
`associations.py` (campaign_promotion, promotion_product) · F3 `promotion_usage.py`
(PromotionUsage, PK·A·T sin SoftDelete). Mixins del template (PrimaryKey/Active/
SoftDelete/Timestamp). PKs/FKs String(36). Las FK forward a `campaign` que viven en
crm/conversations se cierran por ALTER en la migración 0022 (ADR-009).
"""
