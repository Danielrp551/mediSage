"""
Campaign service. Módulo de funciones (no clases), por convención del template.
Hidrata los audit users y los denormalizados `target_vertical_name` (batch vía
vertical_repository.get_by_ids, sin relationship) + `promotions_count` (0 en F1;
el M:N llega en F2). Lanza excepciones de dominio (nunca HTTPException) y NO hace
commit (get_db lo hace al final del request).

`status` es un enum FIJO: las transiciones se validan contra la matriz HARDCODEADA
`CAMPAIGN_TRANSITIONS` (ADR-013, NO una tabla configurable). `transition` no tiene
side-effects ricos (solo setea status + audit) → el endpoint genérico basta.

⚠ SUBSET F1: Campaign aún no tiene el relationship `promotions` (Promotion llega en
F2) → `promotions_count`=0, `CampaignDetail.promotions`=[], y `get_promotions` /
`set_promotions` se posponen a F2.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AlreadyExistsException,
    BadRequestException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.models.vertical import Vertical
from app.modules.catalog.repositories.vertical import vertical_repository
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.marketing.enums import CampaignStatus
from app.modules.marketing.models.campaign import Campaign
from app.modules.marketing.repositories.campaign import campaign_repository
from app.modules.marketing.repositories.promotion import promotion_repository
from app.modules.marketing.schemas.campaign import (
    CampaignCreate,
    CampaignDetail,
    CampaignItem,
    CampaignOption,
    CampaignUpdate,
)
from app.modules.marketing.schemas.promotion import PromotionOption
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now

# Matriz de transición HARDCODEADA (ADR-013, spec §2 — NO una tabla *_transition).
CAMPAIGN_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.draft: {CampaignStatus.active},
    CampaignStatus.active: {CampaignStatus.paused, CampaignStatus.ended},
    CampaignStatus.paused: {CampaignStatus.active, CampaignStatus.ended},
    CampaignStatus.ended: set(),  # terminal
}


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _collect_actor_ids(rows: list[Campaign]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


def _to_item(
    campaign: Campaign,
    audit_users: dict[str, User],
    *,
    vertical_name: str | None,
    promotions_count: int,
) -> CampaignItem:
    return CampaignItem(
        id=campaign.id,
        code=campaign.code,
        name=campaign.name,
        description=campaign.description,
        start_date=campaign.start_date,
        end_date=campaign.end_date,
        status=CampaignStatus(campaign.status),
        target_vertical_id=campaign.target_vertical_id,
        target_vertical_name=vertical_name,
        promotions_count=promotions_count,
        active=campaign.active,
        created_on=campaign.created_on,
        created_by=campaign.created_by,
        created_by_user=_audit_info(audit_users.get(campaign.created_by)),
        updated_on=campaign.updated_on,
        updated_by=campaign.updated_by,
        updated_by_user=_audit_info(audit_users.get(campaign.updated_by)),
    )


def _to_detail(
    campaign: Campaign,
    audit_users: dict[str, User],
    *,
    vertical: Vertical | None,
) -> CampaignDetail:
    # `campaign.promotions` debe venir eager-loaded por el caller (selectinload).
    item = _to_item(
        campaign,
        audit_users,
        vertical_name=(vertical.name if vertical is not None else None),
        promotions_count=len(campaign.promotions),
    )
    return CampaignDetail(
        **item.model_dump(),
        target_vertical=(
            VerticalOption.model_validate(vertical, from_attributes=True)
            if vertical is not None
            else None
        ),
        promotions=[
            PromotionOption.model_validate(p, from_attributes=True) for p in campaign.promotions
        ],
    )


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    # CampaignUpdate declara start_date opcional (date | None), pero la columna es NOT NULL
    # y el create la exige → un `null` explícito es payload inválido, no "sin cambio".
    # Sin este guard, `end_date < None` lanza TypeError → 500 (debe ser 400).
    if start_date is None:
        raise BadRequestException(
            "La fecha de inicio es obligatoria", code="CAMPAIGN_INVALID_DATES"
        )
    if end_date is not None and end_date < start_date:
        raise BadRequestException(
            "La fecha de fin no puede ser anterior a la de inicio",
            code="CAMPAIGN_INVALID_DATES",
        )


async def _resolve_vertical(db: AsyncSession, target_vertical_id: str | None) -> Vertical | None:
    """Carga la vertical objetivo (viva) o None. Lanza si se pidió una inexistente."""
    if target_vertical_id is None:
        return None
    vertical = await vertical_repository.get_by_id(db, target_vertical_id)
    if vertical is None:
        raise BadRequestException(
            "La vertical objetivo no existe", code="TARGET_VERTICAL_NOT_FOUND"
        )
    return vertical


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[CampaignItem]:
    items, total = await campaign_repository.get_paginated(
        db, query_request, load=(selectinload(Campaign.promotions),)
    )
    vertical_ids = [c.target_vertical_id for c in items if c.target_vertical_id is not None]
    verticals = await vertical_repository.get_by_ids(db, vertical_ids)
    vertical_names = {v.id: v.name for v in verticals}
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[
                _to_item(
                    c,
                    audit_users,
                    vertical_name=(
                        vertical_names.get(c.target_vertical_id)
                        if c.target_vertical_id is not None
                        else None
                    ),
                    promotions_count=len(c.promotions),
                )
                for c in items
            ],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def get_by_id(db: AsyncSession, campaign_id: str) -> SingleResponse[CampaignDetail]:
    campaign = await campaign_repository.get_by_id(
        db, campaign_id, load=(selectinload(Campaign.promotions),)
    )
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    vertical = (
        await vertical_repository.get_by_id(db, campaign.target_vertical_id)
        if campaign.target_vertical_id is not None
        else None
    )
    audit_users = await user_repository.get_audit_info_map(
        db, {campaign.created_by, campaign.updated_by}
    )
    return SingleResponse(data=_to_detail(campaign, audit_users, vertical=vertical))


async def list_active(db: AsyncSession) -> list[CampaignOption]:
    rows = await campaign_repository.list_active(db)
    return [CampaignOption.model_validate(r, from_attributes=True) for r in rows]


async def create(
    db: AsyncSession, payload: CampaignCreate, *, actor_id: str
) -> SingleResponse[CampaignDetail]:
    existing = await campaign_repository.get_by_code(db, payload.code)
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe una campaña con el código '{payload.code}'",
            code="CAMPAIGN_CODE_TAKEN",
        )
    _validate_dates(payload.start_date, payload.end_date)
    await _resolve_vertical(db, payload.target_vertical_id)

    now = utc_now()
    campaign = Campaign(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=CampaignStatus.draft.value,
        target_vertical_id=payload.target_vertical_id,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await campaign_repository.create(db, campaign)
    return await get_by_id(db, campaign.id)


async def update(
    db: AsyncSession, campaign_id: str, payload: CampaignUpdate, *, actor_id: str
) -> SingleResponse[CampaignDetail]:
    campaign = await campaign_repository.get_by_id(db, campaign_id)
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    # Inmutables vía update (no los declara el schema; belt-and-suspenders).
    changes.pop("code", None)
    changes.pop("status", None)

    # Validar fechas + vertical sobre el merge (el valor nuevo si vino, sino el existente).
    effective_start = changes.get("start_date", campaign.start_date)
    effective_end = changes["end_date"] if "end_date" in changes else campaign.end_date
    _validate_dates(effective_start, effective_end)
    if "target_vertical_id" in changes:
        await _resolve_vertical(db, changes["target_vertical_id"])

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await campaign_repository.update(db, campaign, changes)
    return await get_by_id(db, campaign_id)


async def transition(
    db: AsyncSession, campaign_id: str, to_status: CampaignStatus, *, actor_id: str
) -> SingleResponse[CampaignDetail]:
    campaign = await campaign_repository.get_by_id(db, campaign_id)
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    current = CampaignStatus(campaign.status)
    if to_status not in CAMPAIGN_TRANSITIONS[current]:
        raise BadRequestException(
            f"Transición de campaña no permitida: de '{current.value}' a '{to_status.value}'",
            code="CAMPAIGN_TRANSITION_NOT_ALLOWED",
        )
    campaign.status = to_status.value
    campaign.updated_by = actor_id
    campaign.updated_on = utc_now()
    await db.flush()
    return await get_by_id(db, campaign_id)


async def remove(db: AsyncSession, campaign_id: str, *, actor_id: str) -> None:
    """Soft-delete LIBRE (sin guard de hijos): los PromotionUsage que referencian la
    campaña son audit histórico y conservan su campaign_id (la fila queda viva, solo
    `deleted_at`); el M:N campaign_promotion persiste (soft-delete no dispara el CASCADE,
    que es solo de hard-delete)."""
    campaign = await campaign_repository.get_by_id(db, campaign_id)
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    campaign.updated_by = actor_id
    campaign.updated_on = utc_now()
    await campaign_repository.soft_delete(db, campaign)


async def get_promotions(
    db: AsyncSession, campaign_id: str
) -> SingleResponse[list[PromotionOption]]:
    campaign = await campaign_repository.get_by_id(
        db, campaign_id, load=(selectinload(Campaign.promotions),)
    )
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    return SingleResponse(
        data=[PromotionOption.model_validate(p, from_attributes=True) for p in campaign.promotions]
    )


async def set_promotions(
    db: AsyncSession, campaign_id: str, promotion_ids: list[str], *, actor_id: str
) -> SingleResponse[CampaignDetail]:
    """Bulk-replace del M:N (relationship directo, mold role/permission). Valida que cada
    promotion_id exista vivo → PROMOTION_NOT_FOUND (404)."""
    campaign = await campaign_repository.get_by_id(
        db, campaign_id, load=(selectinload(Campaign.promotions),)
    )
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    if promotion_ids:
        promos = await promotion_repository.get_by_ids(db, promotion_ids)
        found = {p.id for p in promos}
        missing = [pid for pid in promotion_ids if pid not in found]
        if missing:
            raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
        campaign.promotions = promos
    else:
        campaign.promotions = []
    campaign.updated_by = actor_id
    campaign.updated_on = utc_now()
    await db.flush()
    return await get_by_id(db, campaign_id)
