"""
Servicio del hilo lead de una Person (PersonLeadStatus + LeadStatusHistory).
- create: el lead nace en el estado is_initial (409 ALREADY_HAS_ACTIVE_LEAD si ya
  tiene uno vivo; 400 NO_INITIAL_LEAD_STATUS si el catálogo no define inicial).
- transition: valida la arista contra la matriz F2 (400 LEAD_TRANSITION_NOT_ALLOWED),
  escribe LeadStatusHistory + LeadActivity(STATUS_CHANGE); si el destino es is_final
  CIERRA el lead (soft-delete de PersonLeadStatus) y devuelve data=null.
- get_history: timeline inmutable, resolviendo los estados (incl. soft-deleted) a
  LeadStatusOption para los badges.
Todo en la tx del request (commit al final, rollback si algo lanza).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ActivityType
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_history import LeadStatusHistory
from app.modules.crm.models.person_lead_status import PersonLeadStatus
from app.modules.crm.repositories.lead_status import (
    lead_status_repository,
    lead_status_transition_repository,
)
from app.modules.crm.repositories.lead_status_history import lead_status_history_repository
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.repositories.person_lead_status import person_lead_status_repository
from app.modules.crm.schemas.lead_lifecycle import (
    LeadStatusCreateRequest,
    LeadStatusHistoryItem,
    PersonLeadStatusDetail,
)
from app.modules.crm.schemas.lead_status import LeadStatusOption
from app.modules.crm.services import lead_activity
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


async def _to_lead_detail(db: AsyncSession, lead: PersonLeadStatus) -> PersonLeadStatusDetail:
    status = await lead_status_repository.get_by_id(db, lead.lead_status_id)
    if status is None:  # pragma: no cover - el FK garantiza que exista
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")
    return PersonLeadStatusDetail(
        id=lead.id,
        person_id=lead.person_id,
        lead_status=LeadStatusOption.model_validate(status, from_attributes=True),
        source_campaign_id=lead.source_campaign_id,
        entered_status_at=lead.entered_status_at,
        last_activity_at=lead.last_activity_at,
        created_on=lead.created_on,
    )


async def get_current(
    db: AsyncSession, person_id: str
) -> SingleResponse[PersonLeadStatusDetail | None]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    lead = await person_lead_status_repository.get_active_for_person(db, person_id)
    if lead is None:
        return SingleResponse(data=None)
    return SingleResponse(data=await _to_lead_detail(db, lead))


async def create(
    db: AsyncSession, person_id: str, payload: LeadStatusCreateRequest, *, actor_id: str
) -> SingleResponse[PersonLeadStatusDetail]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    if await person_lead_status_repository.get_active_for_person(db, person_id) is not None:
        raise ConflictException(
            "La persona ya tiene un lead activo", code="ALREADY_HAS_ACTIVE_LEAD"
        )
    initial = await lead_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException(
            "No hay un estado de lead inicial configurado", code="NO_INITIAL_LEAD_STATUS"
        )

    now = utc_now()
    lead = PersonLeadStatus(
        id=generate_uuid(),
        person_id=person_id,
        lead_status_id=initial.id,
        source_campaign_id=payload.source_campaign_id,
        entered_status_at=now,
        last_activity_at=None,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(lead)
    db.add(
        LeadStatusHistory(
            id=generate_uuid(),
            person_id=person_id,
            from_lead_status_id=None,
            to_lead_status_id=initial.id,
            source_campaign_id=payload.source_campaign_id,
            changed_at=now,
            changed_by=actor_id,
            reason=payload.reason,
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
    )
    await db.flush()
    return SingleResponse(data=await _to_lead_detail(db, lead))


async def transition(
    db: AsyncSession, person_id: str, to_id: str, *, actor_id: str, reason: str | None = None
) -> SingleResponse[PersonLeadStatusDetail | None]:
    current = await person_lead_status_repository.get_active_for_person(db, person_id)
    if current is None:
        raise BadRequestException("La persona no tiene un lead activo", code="NO_ACTIVE_LEAD")
    target = await lead_status_repository.get_by_id(db, to_id)
    if target is None:
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")
    if not await lead_status_transition_repository.is_allowed(db, current.lead_status_id, to_id):
        current_status = await lead_status_repository.get_by_id(db, current.lead_status_id)
        current_name = current_status.name if current_status else current.lead_status_id
        raise BadRequestException(
            f"Transición de lead no permitida: de '{current_name}' a '{target.name}'",
            code="LEAD_TRANSITION_NOT_ALLOWED",
        )

    now = utc_now()
    from_id = current.lead_status_id
    db.add(
        LeadStatusHistory(
            id=generate_uuid(),
            person_id=person_id,
            from_lead_status_id=from_id,
            to_lead_status_id=to_id,
            source_campaign_id=None,
            changed_at=now,
            changed_by=actor_id,
            reason=reason,
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
    )
    await lead_activity.log(
        db,
        person_id,
        ActivityType.STATUS_CHANGE,
        advisor_user_id=actor_id,
        actor_id=actor_id,
        payload={"from": from_id, "to": to_id},
    )

    if target.is_final:
        # Cierre: soft-delete de la fila → "lead cerrado" (la traza queda en history).
        current.updated_by = actor_id
        current.updated_on = now
        await person_lead_status_repository.soft_delete(db, current)
        return SingleResponse(data=None)

    current.lead_status_id = to_id
    current.entered_status_at = now
    current.last_activity_at = now
    current.updated_by = actor_id
    current.updated_on = now
    await db.flush()
    return SingleResponse(data=await _to_lead_detail(db, current))


async def get_history(
    db: AsyncSession, person_id: str
) -> SingleResponse[list[LeadStatusHistoryItem]]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    rows = await lead_status_history_repository.list_for_person(db, person_id)

    # Resolver los estados (INCL. soft-deleted — audit trail honesto) para los badges.
    status_ids: set[str] = set()
    for r in rows:
        status_ids.add(r.to_lead_status_id)
        if r.from_lead_status_id is not None:
            status_ids.add(r.from_lead_status_id)
    status_by_id: dict[str, LeadStatus] = {}
    if status_ids:
        result = await db.execute(select(LeadStatus).where(LeadStatus.id.in_(status_ids)))
        status_by_id = {s.id: s for s in result.scalars().all()}

    actor_ids = {r.changed_by for r in rows if r.changed_by is not None}
    audit_users = await user_repository.get_audit_info_map(db, actor_ids)

    def _opt(status_id: str | None) -> LeadStatusOption | None:
        if status_id is None:
            return None
        status = status_by_id.get(status_id)
        return LeadStatusOption.model_validate(status, from_attributes=True) if status else None

    items: list[LeadStatusHistoryItem] = []
    for r in rows:
        to_opt = _opt(r.to_lead_status_id)
        if to_opt is None:  # pragma: no cover - to_lead_status_id es NOT NULL + FK
            continue
        items.append(
            LeadStatusHistoryItem(
                id=r.id,
                person_id=r.person_id,
                from_lead_status=_opt(r.from_lead_status_id),
                to_lead_status=to_opt,
                source_campaign_id=r.source_campaign_id,
                changed_at=r.changed_at,
                changed_by=r.changed_by,
                changed_by_user=(
                    _audit_info(audit_users.get(r.changed_by)) if r.changed_by is not None else None
                ),
                reason=r.reason,
            )
        )
    return SingleResponse(data=items)
