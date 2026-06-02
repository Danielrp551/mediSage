"""
Schemas Pydantic v2 del hilo lead de una Person (PersonLeadStatus) + requests de
ciclo de vida + items del historial. Espeja `frontend/src/types/crm.types.ts`.

- `PersonLeadStatusDetail` lleva la clave **`lead_status`** (NO `status`) con el
  LeadStatusOption denormalizado; shape liviano (sin `active`/`updated_on`).
- `LeadStatusHistoryItem` usa **`from_lead_status`/`to_lead_status`** (NO
  `from_status`/`to_status`), ambos denormalizados a LeadStatusOption.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.schemas.lead_status import LeadStatusOption


class LeadStatusCreateRequest(BaseModel):
    """Body de POST /persons/{id}/lead-status — el lead nace en el estado is_initial;
    solo se suministran origen/razón. source_campaign_id forward (ADR-009)."""

    source_campaign_id: str | None = Field(default=None, max_length=36)
    reason: str | None = Field(default=None, max_length=255)


class LeadStatusTransitionRequest(BaseModel):
    """Body de POST /persons/{id}/lead-status/transition."""

    to_lead_status_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class PersonLeadStatusDetail(BaseModel):
    """Hilo lead actual de una Person (el service devuelve null cuando no hay)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    lead_status: LeadStatusOption  # LeadStatus actual denormalizado (clave `lead_status`)
    source_campaign_id: str | None
    entered_status_at: datetime
    last_activity_at: datetime | None
    created_on: datetime


class LeadStatusHistoryItem(BaseModel):
    """Una fila del timeline de estados de lead. from_lead_status null en la creación."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    from_lead_status: LeadStatusOption | None = None  # denormalizado
    to_lead_status: LeadStatusOption  # denormalizado
    source_campaign_id: str | None
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None
