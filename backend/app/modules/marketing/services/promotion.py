"""
Promotion service. CRUD + validación del descuento en el SERVICE (`_validate_discount`,
create Y update, para que update sin discount_type lo imponga uniforme) + M:N de productos
(join propio, sin relationship en Product) + M:N de campañas (read-only, vía el relationship
`Promotion.campaigns`). Denormaliza products_count/campaigns_count. NO commitea.

⚠ SUBSET F2: `total_uses` = 0 y NO hay `usage_summary` (PromotionUsage + apply llegan en F3).
Cuando `applies_to_all_products`=true, el M:N de productos se IGNORA → products=[]/count=0.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
from app.modules.catalog.models.product import Product
from app.modules.catalog.schemas.product import ProductOption
from app.modules.marketing.enums import DiscountType
from app.modules.marketing.models.promotion import Promotion
from app.modules.marketing.repositories.promotion import promotion_repository
from app.modules.marketing.repositories.promotion_product import promotion_product_repository
from app.modules.marketing.schemas.campaign import CampaignOption
from app.modules.marketing.schemas.promotion import (
    PromotionCreate,
    PromotionDetail,
    PromotionItem,
    PromotionOption,
    PromotionUpdate,
)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now


def _validate_discount(discount_type: DiscountType, discount_value: Decimal) -> None:
    """Rango del descuento (en el SERVICE, no Pydantic). En update, discount_type = el de
    la fila existente (inmutable), discount_value = payload o existente."""
    if discount_type == DiscountType.percentage:
        if not (Decimal("0") < discount_value <= Decimal("100")):
            raise BadRequestException(
                "El porcentaje debe estar entre 0 y 100", code="PROMOTION_INVALID_DISCOUNT"
            )
    else:  # fixed_amount
        if discount_value <= Decimal("0"):
            raise BadRequestException(
                "El monto fijo debe ser mayor que 0", code="PROMOTION_INVALID_DISCOUNT"
            )


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    if start_date is None:
        raise BadRequestException(
            "La fecha de inicio es obligatoria", code="PROMOTION_INVALID_DATES"
        )
    if end_date is not None and end_date < start_date:
        raise BadRequestException(
            "La fecha de fin no puede ser anterior a la de inicio",
            code="PROMOTION_INVALID_DATES",
        )


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _collect_actor_ids(rows: list[Promotion]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


def _to_item(
    promotion: Promotion,
    audit_users: dict[str, User],
    *,
    products_count: int,
    campaigns_count: int,
) -> PromotionItem:
    return PromotionItem(
        id=promotion.id,
        code=promotion.code,
        name=promotion.name,
        description=promotion.description,
        discount_type=DiscountType(promotion.discount_type),
        discount_value=promotion.discount_value,
        currency=promotion.currency,
        start_date=promotion.start_date,
        end_date=promotion.end_date,
        max_uses_total=promotion.max_uses_total,
        max_uses_per_person=promotion.max_uses_per_person,
        applies_to_all_products=promotion.applies_to_all_products,
        # applies_to_all → el M:N se ignora → products_count = 0.
        products_count=0 if promotion.applies_to_all_products else products_count,
        campaigns_count=campaigns_count,
        active=promotion.active,
        created_on=promotion.created_on,
        created_by=promotion.created_by,
        created_by_user=_audit_info(audit_users.get(promotion.created_by)),
        updated_on=promotion.updated_on,
        updated_by=promotion.updated_by,
        updated_by_user=_audit_info(audit_users.get(promotion.updated_by)),
    )


def _to_detail(
    promotion: Promotion,
    audit_users: dict[str, User],
    *,
    products: list[Product],
) -> PromotionDetail:
    # `promotion.campaigns` debe venir eager-loaded por el caller (selectinload).
    item = _to_item(
        promotion,
        audit_users,
        products_count=len(products),
        campaigns_count=len(promotion.campaigns),
    )
    return PromotionDetail(
        **item.model_dump(),
        products=[ProductOption.model_validate(p, from_attributes=True) for p in products],
        campaigns=[
            CampaignOption.model_validate(c, from_attributes=True) for c in promotion.campaigns
        ],
        total_uses=0,  # SUBSET F2: el cómputo real llega en F3.
    )


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[PromotionItem]:
    items, total = await promotion_repository.get_paginated(
        db, query_request, load=(selectinload(Promotion.campaigns),)
    )
    products_count_map = await promotion_product_repository.count_products_map(
        db, [p.id for p in items]
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[
                _to_item(
                    p,
                    audit_users,
                    products_count=products_count_map.get(p.id, 0),
                    campaigns_count=len(p.campaigns),
                )
                for p in items
            ],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def _get_full(db: AsyncSession, promotion_id: str) -> Promotion:
    promotion = await promotion_repository.get_by_id(
        db, promotion_id, load=(selectinload(Promotion.campaigns),)
    )
    if promotion is None:
        raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
    return promotion


async def _detail_response(
    db: AsyncSession, promotion: Promotion
) -> SingleResponse[PromotionDetail]:
    products: list[Product] = (
        []
        if promotion.applies_to_all_products
        else await promotion_product_repository.list_products_for_promotion(db, promotion.id)
    )
    audit_users = await user_repository.get_audit_info_map(
        db, {promotion.created_by, promotion.updated_by}
    )
    return SingleResponse(data=_to_detail(promotion, audit_users, products=products))


async def get_by_id(db: AsyncSession, promotion_id: str) -> SingleResponse[PromotionDetail]:
    promotion = await _get_full(db, promotion_id)
    return await _detail_response(db, promotion)


async def list_active(db: AsyncSession) -> list[PromotionOption]:
    rows = await promotion_repository.list_active(db)
    return [PromotionOption.model_validate(r, from_attributes=True) for r in rows]


async def create(
    db: AsyncSession, payload: PromotionCreate, *, actor_id: str
) -> SingleResponse[PromotionDetail]:
    _validate_discount(payload.discount_type, payload.discount_value)
    _validate_dates(payload.start_date, payload.end_date)
    if await promotion_repository.get_by_code(db, payload.code) is not None:
        raise AlreadyExistsException(
            f"Ya existe una promoción con el código '{payload.code}'",
            code="PROMOTION_CODE_TAKEN",
        )
    now = utc_now()
    promotion = Promotion(
        id=generate_uuid(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        discount_type=payload.discount_type.value,
        discount_value=payload.discount_value,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
        max_uses_total=payload.max_uses_total,
        max_uses_per_person=payload.max_uses_per_person,
        applies_to_all_products=payload.applies_to_all_products,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await promotion_repository.create(db, promotion)
    return await get_by_id(db, promotion.id)


async def update(
    db: AsyncSession, promotion_id: str, payload: PromotionUpdate, *, actor_id: str
) -> SingleResponse[PromotionDetail]:
    promotion = await _get_full(db, promotion_id)
    changes = payload.model_dump(exclude_unset=True)
    # Inmutables vía update (no los declara el schema; belt-and-suspenders).
    changes.pop("code", None)
    changes.pop("discount_type", None)

    # Nulls EXPLÍCITOS sobre columnas NOT NULL = input inválido (no "sin cambio"). Sin este
    # guard: discount_value=None → _validate_discount(Decimal < None) → TypeError → 500;
    # currency=None → setattr sobre columna NOT NULL → IntegrityError → 500. Deben ser 400.
    if "discount_value" in changes and changes["discount_value"] is None:
        raise BadRequestException(
            "El valor del descuento es obligatorio", code="PROMOTION_INVALID_DISCOUNT"
        )
    if "currency" in changes and changes["currency"] is None:
        raise BadRequestException("La moneda es obligatoria", code="PROMOTION_INVALID_DISCOUNT")

    # Rango del descuento sobre el merge (discount_type = el existente, inmutable).
    effective_value = changes.get("discount_value", promotion.discount_value)
    _validate_discount(DiscountType(promotion.discount_type), effective_value)
    # Fechas sobre el merge.
    effective_start = changes.get("start_date", promotion.start_date)
    effective_end = changes["end_date"] if "end_date" in changes else promotion.end_date
    _validate_dates(effective_start, effective_end)

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await promotion_repository.update(db, promotion, changes)
    return await get_by_id(db, promotion_id)


async def remove(db: AsyncSession, promotion_id: str, *, actor_id: str) -> None:
    promotion = await promotion_repository.get_by_id(db, promotion_id)
    if promotion is None:
        raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
    promotion.updated_by = actor_id
    promotion.updated_on = utc_now()
    await promotion_repository.soft_delete(db, promotion)


async def get_products(db: AsyncSession, promotion_id: str) -> SingleResponse[list[ProductOption]]:
    await _get_full(db, promotion_id)  # 404 si no existe
    products = await promotion_product_repository.list_products_for_promotion(db, promotion_id)
    return SingleResponse(
        data=[ProductOption.model_validate(p, from_attributes=True) for p in products]
    )


async def set_products(
    db: AsyncSession, promotion_id: str, product_ids: list[str], *, actor_id: str
) -> SingleResponse[PromotionDetail]:
    promotion = await _get_full(db, promotion_id)
    if product_ids:
        found = await promotion_product_repository.live_product_ids(db, product_ids)
        missing = [pid for pid in product_ids if pid not in found]
        if missing:
            raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    await promotion_product_repository.set_products(db, promotion_id, product_ids)
    promotion.updated_by = actor_id
    promotion.updated_on = utc_now()
    await db.flush()
    return await get_by_id(db, promotion_id)
