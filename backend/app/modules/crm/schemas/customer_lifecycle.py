"""
Schemas Pydantic v2 del hilo cliente de una Person (PersonCustomerStatus) + requests
de ciclo de vida + items del historial. Espeja `frontend/src/types/crm.types.ts`.

- `PersonCustomerStatusDetail` lleva la clave **`customer_status`** (NO `status`) con
  el CustomerStatusOption denormalizado; trae `became_customer_at` (primera vez) +
  `entered_status_at` (estado actual) + `created_on`; shape liviano (sin
  `active`/`updated_on`).
- `CustomerStatusHistoryItem` usa **`from_customer_status`/`to_customer_status`**,
  ambos denormalizados a CustomerStatusOption (igual que el hilo lead emite
  LeadStatusOption en su history — sin drift Summary↔Option).
- El cliente NO se crea "desde cero": nace vía `promote-to-customer` (desde el lead).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.schemas.customer_status import CustomerStatusOption


class CustomerStatusTransitionRequest(BaseModel):
    """Body de POST /persons/{id}/customer-status/transition."""

    to_customer_status_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class PromoteToCustomerRequest(BaseModel):
    """Body (opcional) de POST /persons/{id}/promote-to-customer — el cliente nace en
    el estado is_initial; solo se suministra una razón opcional."""

    reason: str | None = Field(default=None, max_length=255)


class PersonCustomerStatusDetail(BaseModel):
    """Hilo cliente actual de una Person (el service devuelve null cuando no hay)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    customer_status: CustomerStatusOption  # estado actual denormalizado (clave `customer_status`)
    became_customer_at: datetime
    entered_status_at: datetime
    created_on: datetime


class CustomerStatusHistoryItem(BaseModel):
    """Una fila del timeline de estados de cliente. from_customer_status null en la
    promoción inicial."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    from_customer_status: CustomerStatusOption | None = None  # denormalizado
    to_customer_status: CustomerStatusOption  # denormalizado
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None
