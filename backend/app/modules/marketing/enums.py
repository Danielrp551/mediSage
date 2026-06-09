"""
Marketing enums (value sets a nivel de código, NO catálogos en BD).

- CampaignStatus: ciclo de vida FIJO de una campaña (draft→active→paused/ended).
  Persistido como varchar(20). Las transiciones se validan en el SERVICE contra
  una matriz HARDCODEADA (NO una tabla *_transition configurable — diverge de
  crm/scheduling; decisión #2 / ADR-013: 4 estados inherentes que la clínica no
  reconfigura).
- DiscountType: cómo se calcula el descuento de una promoción. INMUTABLE
  post-create (no se puede cambiar percentage↔fixed_amount). Persistido como
  varchar(20). (Lo usa Promotion en F2; PromotionOption lo expone desde F1.)
"""

from __future__ import annotations

from enum import StrEnum


class CampaignStatus(StrEnum):
    draft = "draft"
    active = "active"
    paused = "paused"
    ended = "ended"


class DiscountType(StrEnum):
    percentage = "percentage"
    fixed_amount = "fixed_amount"
