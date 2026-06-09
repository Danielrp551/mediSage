"""Schemas Pydantic v2 de `marketing` (skeleton inerte en F0).

Por fase: F1 `campaign.py` (Option/Item/Detail/Create/Update + Transition +
PromotionsReplace) · F2 `promotion.py` (discount discriminado + ProductsReplace) ·
F3 `promotion_usage.py` (Item/Detail + Apply + Eligibility + ComputePrice + Summary).
Decimales (`Numeric(10,2)`) se serializan como string en el wire.
"""
