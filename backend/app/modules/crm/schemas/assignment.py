"""
Schemas Pydantic v2 de la asignación de owner (LeadAssignment) + el dropdown de
asesores (AdvisorOption) + la bandeja del asesor (MyLeadItem). Espeja
`frontend/src/types/crm.types.ts`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.schemas.person import LeadStatusSummary, PersonPrimaryIdentifier


class AssignmentRequest(BaseModel):
    """Body de PUT /persons/{id}/assignment — asignación manual / "asignarme"."""

    advisor_user_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class LeadAssignmentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    advisor: UserAuditInfo  # denormalizado del user
    assigned_at: datetime
    assigned_by: str | None
    assigned_by_user: UserAuditInfo | None = None
    reason: str | None


class AdvisorOption(BaseModel):
    """Asesor para el dropdown de reasignación / filtro — GET /advisors/active.
    `id` es el user.id (lo que espera advisor_user_id en PUT /assignment)."""

    id: str
    full_name: str


class MyLeadItem(BaseModel):
    """Fila de la bandeja del asesor (POST /me/leads/list). Denormaliza el próximo
    seguimiento pendiente para resaltarlo en la lista."""

    person_id: str
    full_name: str
    primary_identifier: PersonPrimaryIdentifier | None = None
    lead_status: LeadStatusSummary | None = None
    last_activity_at: datetime | None = None
    next_follow_up_at: datetime | None = None
