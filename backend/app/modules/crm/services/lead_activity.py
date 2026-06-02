"""
LeadActivity service. En F3 expone el helper interno `log` (lo reusan
person_lead_status.transition → STATUS_CHANGE y lead_assignment.reassign/
assign_round_robin → REASSIGNED) y la lectura del feed (`list_for_person`) que
alimenta el tab Actividad (Iteración A, read-only). El composer del asesor
(create/update/delete de NOTE/CALL_ATTEMPT/FOLLOW_UP_*) llega en F5.

`log` además toca `last_activity_at` del lead activo (denormalizado) si existe.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ActivityOutcome, ActivityType
from app.modules.crm.models.lead_activity import LeadActivity
from app.modules.crm.repositories.lead_activity import lead_activity_repository
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.repositories.person_lead_status import person_lead_status_repository
from app.modules.crm.schemas.activity import ActivityItem, ActivityListRequest
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(activity: LeadActivity, audit_users: dict[str, User]) -> ActivityItem:
    return ActivityItem(
        id=activity.id,
        person_id=activity.person_id,
        activity_type=ActivityType(activity.activity_type),
        advisor_user_id=activity.advisor_user_id,
        advisor=(
            _audit_info(audit_users.get(activity.advisor_user_id))
            if activity.advisor_user_id is not None
            else None
        ),
        content=activity.content,
        scheduled_for=activity.scheduled_for,
        completed_at=activity.completed_at,
        outcome=ActivityOutcome(activity.outcome) if activity.outcome else None,
        payload=activity.payload,
        related_appointment_id=activity.related_appointment_id,
        related_conversation_id=activity.related_conversation_id,
        active=activity.active,
        created_on=activity.created_on,
        created_by=activity.created_by,
        created_by_user=_audit_info(audit_users.get(activity.created_by)),
        updated_on=activity.updated_on,
        updated_by=activity.updated_by,
        updated_by_user=_audit_info(audit_users.get(activity.updated_by)),
    )


def _collect_actor_ids(rows: list[LeadActivity]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
        if row.advisor_user_id is not None:
            ids.add(row.advisor_user_id)
    return ids


async def log(
    db: AsyncSession,
    person_id: str,
    activity_type: ActivityType,
    *,
    advisor_user_id: str | None,
    actor_id: str,
    content: str | None = None,
    scheduled_for: datetime | None = None,
    completed_at: datetime | None = None,
    outcome: ActivityOutcome | None = None,
    payload: dict[str, Any] | None = None,
) -> LeadActivity:
    """Helper interno: inserta una LeadActivity y, si la persona tiene lead activo,
    actualiza su `last_activity_at` (denormalizado). NO hace flush/commit (lo decide
    el caller / el request)."""
    now = utc_now()
    activity = LeadActivity(
        id=generate_uuid(),
        person_id=person_id,
        advisor_user_id=advisor_user_id,
        activity_type=activity_type.value,
        content=content,
        scheduled_for=scheduled_for,
        completed_at=completed_at,
        outcome=outcome.value if outcome else None,
        payload=payload,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(activity)
    lead = await person_lead_status_repository.get_active_for_person(db, person_id)
    if lead is not None:
        lead.last_activity_at = now
        lead.updated_by = actor_id
        lead.updated_on = now
    return activity


async def list_for_person(
    db: AsyncSession, person_id: str, payload: ActivityListRequest
) -> SingleResponse[list[ActivityItem]]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    types = [t.value for t in payload.activity_type] if payload.activity_type else None
    rows = await lead_activity_repository.list_for_person(
        db, person_id, activity_types=types, date_from=payload.date_from, date_to=payload.date_to
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(rows))
    return SingleResponse(data=[_to_item(r, audit_users) for r in rows])
