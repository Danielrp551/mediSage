"""
Servicio del hilo cliente de una Person (PersonCustomerStatus + CustomerStatusHistory).
- promote_from_lead: el cliente nace en el estado is_initial (409 ALREADY_CUSTOMER si
  ya es cliente; 400 NO_INITIAL_CUSTOMER_STATUS si el catálogo no define inicial).
  Si la persona tiene un lead activo y su estado puede alcanzar un estado is_won por
  la matriz, CIERRA ese lead como ganado (reusa person_lead_status.transition →
  LeadStatusHistory + STATUS_CHANGE + soft-delete por is_final). Si no hay ganado
  alcanzable, deja el lead abierto (ADR-003: lead y cliente conviven).
- transition: valida la arista contra la matriz customer F2 (400
  CUSTOMER_TRANSITION_NOT_ALLOWED), escribe CustomerStatusHistory; si el destino es
  is_final CIERRA el cliente (soft-delete) y devuelve data=null. NO emite LeadActivity
  (el feed/STATUS_CHANGE es del hilo lead; la traza customer vive en su history).
- get_history: timeline inmutable, resolviendo los estados (incl. soft-deleted) a
  CustomerStatusOption para los badges.
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
from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.customer_status_history import CustomerStatusHistory
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.crm.repositories.customer_status import (
    customer_status_repository,
    customer_status_transition_repository,
)
from app.modules.crm.repositories.customer_status_history import (
    customer_status_history_repository,
)
from app.modules.crm.repositories.lead_status import (
    lead_status_repository,
    lead_status_transition_repository,
)
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.repositories.person_customer_status import (
    person_customer_status_repository,
)
from app.modules.crm.repositories.person_lead_status import person_lead_status_repository
from app.modules.crm.schemas.customer_lifecycle import (
    CustomerStatusHistoryItem,
    PersonCustomerStatusDetail,
)
from app.modules.crm.schemas.customer_status import CustomerStatusOption
from app.modules.crm.services import person_lead_status as person_lead_status_service
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


async def _to_customer_detail(
    db: AsyncSession, customer: PersonCustomerStatus
) -> PersonCustomerStatusDetail:
    status = await customer_status_repository.get_by_id(db, customer.customer_status_id)
    if status is None:  # pragma: no cover - el FK garantiza que exista
        raise NotFoundException("Estado de cliente no encontrado", code="CUSTOMER_STATUS_NOT_FOUND")
    return PersonCustomerStatusDetail(
        id=customer.id,
        person_id=customer.person_id,
        customer_status=CustomerStatusOption.model_validate(status, from_attributes=True),
        became_customer_at=customer.became_customer_at,
        entered_status_at=customer.entered_status_at,
        created_on=customer.created_on,
    )


async def get_current(
    db: AsyncSession, person_id: str
) -> SingleResponse[PersonCustomerStatusDetail | None]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    customer = await person_customer_status_repository.get_active_for_person(db, person_id)
    if customer is None:
        return SingleResponse(data=None)
    return SingleResponse(data=await _to_customer_detail(db, customer))


async def _close_won_lead_if_possible(db: AsyncSession, person_id: str, *, actor_id: str) -> None:
    """Cierra el lead activo COMO GANADO si su estado actual puede alcanzar un estado
    is_won por la matriz (reusa la transición de lead → history + STATUS_CHANGE +
    soft-delete por is_final). Si no hay ganado alcanzable, NO toca el lead (queda
    abierto; ADR-003 permite lead + cliente a la vez)."""
    current = await person_lead_status_repository.get_active_for_person(db, person_id)
    if current is None:
        return
    current_status = await lead_status_repository.get_by_id(db, current.lead_status_id)
    if current_status is not None and current_status.is_won:
        # Defensivo (no debería ocurrir: is_won ⟹ is_final ⟹ ya cerrado al entrar):
        # ya está en un estado ganado → cerrar directamente.
        now = utc_now()
        current.updated_by = actor_id
        current.updated_on = now
        await person_lead_status_repository.soft_delete(db, current)
        return
    outgoing_ids = await lead_status_transition_repository.list_outgoing(db, current.lead_status_id)
    reachable = await lead_status_repository.get_by_ids(db, outgoing_ids)
    won = next((s for s in reachable if s.is_won), None)
    if won is None:
        return
    # is_won ⟹ is_final → la transición soft-deletea el lead (lo cierra como ganado).
    await person_lead_status_service.transition(
        db, person_id, won.id, actor_id=actor_id, reason="Promovido a cliente"
    )


async def promote_from_lead(
    db: AsyncSession, person_id: str, *, actor_id: str, reason: str | None = None
) -> SingleResponse[PersonCustomerStatusDetail]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    if await person_customer_status_repository.get_active_for_person(db, person_id) is not None:
        raise ConflictException("La persona ya es cliente", code="ALREADY_CUSTOMER")
    initial = await customer_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException(
            "No hay un estado de cliente inicial configurado",
            code="NO_INITIAL_CUSTOMER_STATUS",
        )

    now = utc_now()
    customer = PersonCustomerStatus(
        id=generate_uuid(),
        person_id=person_id,
        customer_status_id=initial.id,
        became_customer_at=now,
        entered_status_at=now,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(customer)
    db.add(
        CustomerStatusHistory(
            id=generate_uuid(),
            person_id=person_id,
            from_customer_status_id=None,
            to_customer_status_id=initial.id,
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
    # Cerrar el lead como ganado si el estado actual lo permite (matriz).
    await _close_won_lead_if_possible(db, person_id, actor_id=actor_id)
    await db.flush()
    return SingleResponse(data=await _to_customer_detail(db, customer))


async def transition(
    db: AsyncSession, person_id: str, to_id: str, *, actor_id: str, reason: str | None = None
) -> SingleResponse[PersonCustomerStatusDetail | None]:
    current = await person_customer_status_repository.get_active_for_person(db, person_id)
    if current is None:
        raise BadRequestException("La persona no es cliente", code="NOT_A_CUSTOMER")
    target = await customer_status_repository.get_by_id(db, to_id)
    if target is None:
        raise NotFoundException("Estado de cliente no encontrado", code="CUSTOMER_STATUS_NOT_FOUND")
    if not await customer_status_transition_repository.is_allowed(
        db, current.customer_status_id, to_id
    ):
        current_status = await customer_status_repository.get_by_id(db, current.customer_status_id)
        current_name = current_status.name if current_status else current.customer_status_id
        raise BadRequestException(
            f"Transición de cliente no permitida: de '{current_name}' a '{target.name}'",
            code="CUSTOMER_TRANSITION_NOT_ALLOWED",
        )

    now = utc_now()
    from_id = current.customer_status_id
    db.add(
        CustomerStatusHistory(
            id=generate_uuid(),
            person_id=person_id,
            from_customer_status_id=from_id,
            to_customer_status_id=to_id,
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

    if target.is_final:
        # Cierre: soft-delete de la fila → "cliente cerrado" (la traza queda en history).
        current.updated_by = actor_id
        current.updated_on = now
        await person_customer_status_repository.soft_delete(db, current)
        return SingleResponse(data=None)

    current.customer_status_id = to_id
    current.entered_status_at = now
    current.updated_by = actor_id
    current.updated_on = now
    await db.flush()
    return SingleResponse(data=await _to_customer_detail(db, current))


async def get_history(
    db: AsyncSession, person_id: str
) -> SingleResponse[list[CustomerStatusHistoryItem]]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    rows = await customer_status_history_repository.list_for_person(db, person_id)

    # Resolver los estados (INCL. soft-deleted — audit trail honesto) para los badges.
    status_ids: set[str] = set()
    for r in rows:
        status_ids.add(r.to_customer_status_id)
        if r.from_customer_status_id is not None:
            status_ids.add(r.from_customer_status_id)
    status_by_id: dict[str, CustomerStatus] = {}
    if status_ids:
        result = await db.execute(select(CustomerStatus).where(CustomerStatus.id.in_(status_ids)))
        status_by_id = {s.id: s for s in result.scalars().all()}

    actor_ids = {r.changed_by for r in rows if r.changed_by is not None}
    audit_users = await user_repository.get_audit_info_map(db, actor_ids)

    def _opt(status_id: str | None) -> CustomerStatusOption | None:
        if status_id is None:
            return None
        status = status_by_id.get(status_id)
        return CustomerStatusOption.model_validate(status, from_attributes=True) if status else None

    items: list[CustomerStatusHistoryItem] = []
    for r in rows:
        to_opt = _opt(r.to_customer_status_id)
        if to_opt is None:  # pragma: no cover - to_customer_status_id es NOT NULL + FK
            continue
        items.append(
            CustomerStatusHistoryItem(
                id=r.id,
                person_id=r.person_id,
                from_customer_status=_opt(r.from_customer_status_id),
                to_customer_status=to_opt,
                changed_at=r.changed_at,
                changed_by=r.changed_by,
                changed_by_user=(
                    _audit_info(audit_users.get(r.changed_by)) if r.changed_by is not None else None
                ),
                reason=r.reason,
            )
        )
    return SingleResponse(data=items)
