"""Módulo `marketing` (#8, ÚLTIMO): campañas (atribución de leads) + promociones
(descuentos sobre productos del catálogo) + traza de uso inmutable.

Entidades (5): Campaign · Promotion (discount discriminado) · PromotionUsage
(audit inmutable, PK·A·T sin SoftDelete) · M:N campaign_promotion · promotion_product.

Depende de `catalog` (Product/Vertical) y `crm` (Person), ambos en prod.

⚠ ESTADO F0 (Prep): este paquete es un **skeleton inerte** — solo docstrings, sin
modelos/routers. **NO está registrado** en `app/modules/__init__.py` ni en
`app/main.py`, así que NINGUNA ruta `/api/v1/marketing/*` se monta todavía (dan 404).
Cada fase agrega su código y F1 cablea el registro:
  - F1: Campaign (CRUD + status enum + transition) + ALTER que CIERRA las 3 FK forward
        a `campaign` (crm.person_lead_status/lead_status_history.source_campaign_id +
        conversations.channel_account.default_campaign_id, ADR-009). Registra el módulo.
  - F2: Promotion (discount discriminado) + M:N campaign_promotion / promotion_product.
  - F3: PromotionUsage + apply/validate/eligible-for/compute-price + reportes.
  - F4: wire atómico `apply_promotion_id` en scheduling.create_appointment + bot tool
        list_eligible_promotions (ADR-013).

Decisiones de diseño en docs/decisions/ADR-013 y docs/modules/marketing/.
"""
