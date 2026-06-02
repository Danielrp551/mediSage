"""
Schemas Pydantic v2 del timeline (LeadActivity). El POST público solo admite los
tipos que emite el asesor (`ADVISOR_ACTIVITY_TYPES`); el resto (STATUS_CHANGE,
REASSIGNED, CAMPAIGN_ATTRIBUTION, y los cross-module) los emite el sistema vía el
helper `lead_activity.log`. `ActivityItem` incluye `advisor_user_id` (FK lógica
cruda) + `advisor` denormalizado + audit cols (LeadActivity tiene TimestampMixin,
SIN SoftDelete). Espeja `frontend/src/types/crm.types.ts`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ActivityOutcome, ActivityType

# Tipos que un asesor puede crear vía la API pública (el resto es sistema/cross-module).
ADVISOR_ACTIVITY_TYPES = {
    ActivityType.NOTE,
    ActivityType.CALL_ATTEMPT,
    ActivityType.FOLLOW_UP_SCHEDULED,
    ActivityType.FOLLOW_UP_COMPLETED,
}


class ActivityCreate(BaseModel):
    """POST /persons/{id}/activities — solo tipos emitidos por el asesor."""

    activity_type: ActivityType
    content: str | None = None
    scheduled_for: datetime | None = None
    completed_at: datetime | None = None
    outcome: ActivityOutcome | None = None
    payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _advisor_type_only(self) -> ActivityCreate:
        if self.activity_type not in ADVISOR_ACTIVITY_TYPES:
            raise ValueError("activity_type not allowed via this endpoint")
        if self.activity_type == ActivityType.FOLLOW_UP_SCHEDULED and self.scheduled_for is None:
            raise ValueError("scheduled_for is required for FOLLOW_UP_SCHEDULED")
        return self


class ActivityUpdate(BaseModel):
    """PUT /persons/{id}/activities/{act_id} — solo estos campos son editables."""

    content: str | None = None
    outcome: ActivityOutcome | None = None
    completed_at: datetime | None = None
    scheduled_for: datetime | None = None


class ActivityListRequest(BaseModel):
    """Body de POST /persons/{id}/activities/list — filtros tipados del timeline."""

    activity_type: list[ActivityType] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    activity_type: ActivityType
    advisor_user_id: str | None  # FK lógica cruda (null/SYSTEM → actividad de sistema)
    advisor: UserAuditInfo | None = None  # denormalizado; null en eventos solo-SYSTEM
    content: str | None
    scheduled_for: datetime | None
    completed_at: datetime | None
    outcome: ActivityOutcome | None
    payload: dict[str, Any] | None
    related_appointment_id: str | None
    related_conversation_id: str | None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
