"""
Servicio de asignación de owner (LeadAssignment) + bandeja del asesor.
- get_current: el owner vivo (404 ASSIGNMENT_NOT_FOUND).
- reassign: manual / "asignarme" — valida ASESOR (400 ADVISOR_NOT_FOUND /
  ADVISOR_NOT_ASESOR); soft-delete del actual + insert + LeadActivity(REASSIGNED), 1 tx.
- assign_round_robin: auto por carga (SELECT … FOR UPDATE); idempotente si ya hay
  owner; 400 NO_ADVISOR_AVAILABLE si no hay asesor.
- list_advisors: asesores activos para el dropdown (GET /advisors/active).
- list_my_leads: leads del asesor logueado (MyLeadItem, con próximo seguimiento).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ActivityType
from app.modules.crm.models.lead_assignment import LeadAssignment
from app.modules.crm.models.person import Person
from app.modules.crm.repositories.lead_activity import lead_activity_repository
from app.modules.crm.repositories.lead_assignment import lead_assignment_repository
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.repositories.person_lead_status import person_lead_status_repository
from app.modules.crm.schemas.assignment import AdvisorOption, LeadAssignmentDetail, MyLeadItem
from app.modules.crm.schemas.person import LeadStatusSummary, PersonPrimaryIdentifier
from app.modules.crm.services import lead_activity
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _full_name(person: Person) -> str:
    return f"{person.first_name} {person.last_name} {person.second_last_name or ''}".strip()


async def _build_detail(db: AsyncSession, assignment: LeadAssignment) -> LeadAssignmentDetail:
    ids: set[str] = {assignment.advisor_user_id}
    if assignment.assigned_by is not None:
        ids.add(assignment.assigned_by)
    audit_users = await user_repository.get_audit_info_map(db, ids)
    advisor = _audit_info(audit_users.get(assignment.advisor_user_id))
    if advisor is None:  # pragma: no cover - advisor_user_id es FK NOT NULL a user
        raise NotFoundException("Asesor no encontrado", code="ADVISOR_NOT_FOUND")
    return LeadAssignmentDetail(
        id=assignment.id,
        person_id=assignment.person_id,
        advisor=advisor,
        assigned_at=assignment.assigned_at,
        assigned_by=assignment.assigned_by,
        assigned_by_user=(
            _audit_info(audit_users.get(assignment.assigned_by))
            if assignment.assigned_by is not None
            else None
        ),
        reason=assignment.reason,
    )


async def _require_person(db: AsyncSession, person_id: str) -> None:
    if await person_repository.get_by_id(db, person_id) is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")


async def get_current(db: AsyncSession, person_id: str) -> SingleResponse[LeadAssignmentDetail]:
    await _require_person(db, person_id)
    assignment = await lead_assignment_repository.get_active_for_person(db, person_id)
    if assignment is None:
        raise NotFoundException(
            "La persona no tiene un asesor asignado", code="ASSIGNMENT_NOT_FOUND"
        )
    return SingleResponse(data=await _build_detail(db, assignment))


async def reassign(
    db: AsyncSession,
    person_id: str,
    advisor_user_id: str,
    *,
    actor_id: str,
    reason: str | None = None,
) -> SingleResponse[LeadAssignmentDetail]:
    await _require_person(db, person_id)
    advisor = await user_repository.get_by_id(db, advisor_user_id)
    if advisor is None or not advisor.active:
        raise BadRequestException("Asesor no encontrado", code="ADVISOR_NOT_FOUND")
    if not await user_repository.has_role(db, advisor_user_id, "ASESOR"):
        raise BadRequestException("El usuario no tiene el rol ASESOR", code="ADVISOR_NOT_ASESOR")

    current = await lead_assignment_repository.get_active_for_person(db, person_id)
    if current is not None and current.advisor_user_id == advisor_user_id:
        # Idempotente: ya es el owner → no-op (no rota la fila ni emite REASSIGNED espurio).
        return SingleResponse(data=await _build_detail(db, current))

    now = utc_now()
    if current is not None:
        # Libera el UNIQUE parcial ANTES de insertar la fila nueva (soft_delete flushea).
        current.updated_by = actor_id
        current.updated_on = now
        await lead_assignment_repository.soft_delete(db, current)
    new_assignment = LeadAssignment(
        id=generate_uuid(),
        person_id=person_id,
        advisor_user_id=advisor_user_id,
        assigned_at=now,
        assigned_by=actor_id,
        reason=reason,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(new_assignment)
    await lead_activity.log(
        db,
        person_id,
        ActivityType.REASSIGNED,
        advisor_user_id=advisor_user_id,
        actor_id=actor_id,
        payload={"by": actor_id, "reason": reason},
    )
    await db.flush()
    return SingleResponse(data=await _build_detail(db, new_assignment))


async def assign_round_robin(
    db: AsyncSession, person_id: str, *, actor_id: str
) -> SingleResponse[LeadAssignmentDetail]:
    await _require_person(db, person_id)
    current = await lead_assignment_repository.get_active_for_person(db, person_id)
    if current is not None:
        # Idempotente: ya tiene owner → devuelve el actual sin reasignar.
        return SingleResponse(data=await _build_detail(db, current))
    advisor_id = await lead_assignment_repository.pick_round_robin_advisor(db)
    if advisor_id is None:
        raise BadRequestException(
            "No hay asesores disponibles para asignar", code="NO_ADVISOR_AVAILABLE"
        )
    now = utc_now()
    new_assignment = LeadAssignment(
        id=generate_uuid(),
        person_id=person_id,
        advisor_user_id=advisor_id,
        assigned_at=now,
        assigned_by=None,  # auto (round-robin)
        reason=None,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(new_assignment)
    await lead_activity.log(
        db,
        person_id,
        ActivityType.REASSIGNED,
        advisor_user_id=advisor_id,
        actor_id=actor_id,
        payload={"by": None, "auto": True},
    )
    await db.flush()
    return SingleResponse(data=await _build_detail(db, new_assignment))


async def list_advisors(db: AsyncSession) -> list[AdvisorOption]:
    users = await user_repository.list_active_by_role(db, "ASESOR")
    return [AdvisorOption(id=u.id, full_name=u.full_name) for u in users]


async def list_my_leads(
    db: AsyncSession, advisor_user_id: str, query_request: QueryRequest
) -> PaginatedResponse[MyLeadItem]:
    items, total = await person_repository.list_paginated_filtered(
        db, query_request, advisor_user_id=advisor_user_id, has_active_lead=True
    )
    person_ids = [p.id for p in items]
    primary_map = await person_repository.primary_identifier_map(db, person_ids)
    status_map = await person_lead_status_repository.status_map(db, person_ids)
    last_activity_map = await person_lead_status_repository.last_activity_map(db, person_ids)
    follow_up_map = await lead_activity_repository.next_follow_up_map(db, person_ids, utc_now())

    rows = [
        MyLeadItem(
            person_id=p.id,
            full_name=_full_name(p),
            primary_identifier=(
                PersonPrimaryIdentifier.model_validate(primary_map[p.id], from_attributes=True)
                if p.id in primary_map
                else None
            ),
            lead_status=(
                LeadStatusSummary.model_validate(status_map[p.id], from_attributes=True)
                if p.id in status_map
                else None
            ),
            last_activity_at=last_activity_map.get(p.id),
            next_follow_up_at=follow_up_map.get(p.id),
        )
        for p in items
    ]
    return PaginatedResponse(
        data=PaginatedData(
            items=rows,
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )
