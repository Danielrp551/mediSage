"""
promotion_usage service — el corazón de F3.

`apply` crea un PromotionUsage (redención INMUTABLE) validando promo/product/person +
vigencia + cobertura + no-stacking + límites, y snapshoteando original/discount/final +
currency. NO commitea (atómico cuando lo invoca scheduling.create_appointment en F4,
ADR-013 D2). `eligible_for`/`validate`/`compute_price` son lecturas (NO insertan).

La lógica de elegibilidad (vigencia/cobertura/límites) vive en `_ineligibility_reason`,
compartida por `apply` (que la LANZA como excepción de dominio) y los read-paths (que la
DEVUELVEN como `reason`, is_eligible=false). El cálculo del descuento vive en
`_compute_discount` (puro, Decimal, ROUND_HALF_UP, cap a base_price).

Decisión confirmada: `compute_price` NO impone elegibilidad — calcula el descuento que la
promo daría (math). La elegibilidad la dan `validate`/`eligible_for`; `apply` es el gate
duro. product/person/promo inexistentes SÍ lanzan 404 (input inválido, no inelegibilidad).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import NoReturn

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
from app.modules.catalog.models.product import Product
from app.modules.catalog.repositories.product import (
    product_repository as catalog_product_repository,
)
from app.modules.crm.repositories.person import person_repository
from app.modules.crm.services.person import person_option_map
from app.modules.marketing.enums import DiscountType
from app.modules.marketing.models.promotion import Promotion
from app.modules.marketing.models.promotion_usage import PromotionUsage
from app.modules.marketing.repositories.campaign import campaign_repository
from app.modules.marketing.repositories.promotion import promotion_repository
from app.modules.marketing.repositories.promotion_product import promotion_product_repository
from app.modules.marketing.repositories.promotion_usage import promotion_usage_repository
from app.modules.marketing.schemas.promotion import PromotionOption
from app.modules.marketing.schemas.promotion_usage import (
    ComputePriceResponse,
    PromotionEligibility,
    PromotionUsageDetail,
    PromotionUsageItem,
)
from app.modules.scheduling.models.appointment import Appointment  # FK existence (read)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now

# Motivos de inelegibilidad → mensaje en español (todos 400 BadRequest). apply los lanza;
# los read-paths los devuelven como `reason` (is_eligible=false).
_INELIGIBILITY_DETAIL: dict[str, str] = {
    "PROMOTION_NOT_ACTIVE": "La promoción no está activa",
    "PROMOTION_EXPIRED": "La promoción está fuera de vigencia",
    "PROMOTION_PRODUCT_NOT_COVERED": "La promoción no cubre este producto",
    "PROMOTION_LIMIT_REACHED": "La promoción alcanzó su límite de usos",
    "PROMOTION_PERSON_LIMIT_REACHED": "La persona alcanzó su límite de usos de la promoción",
}


# ── Cálculo + elegibilidad (compartidos por apply y los read-paths) ──────────────────


def _compute_discount(promo: Promotion, base_price: Decimal) -> Decimal:
    """Puro, testeable. percentage: base_price * value/100 (ROUND_HALF_UP 2dp), cap a
    base_price. fixed_amount: min(value, base_price). Un descuento NUNCA supera el precio."""
    if promo.discount_type == DiscountType.percentage.value:
        raw = base_price * promo.discount_value / Decimal("100")
        discount = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:  # fixed_amount
        discount = promo.discount_value
    return min(discount, base_price)


def _promo_active_reason(promo: Promotion) -> str | None:
    """Vigencia de la promo: activa + dentro de fechas. Code o None (date puro, sin tz)."""
    today = date.today()
    if not promo.active:
        return "PROMOTION_NOT_ACTIVE"
    if promo.start_date > today or (promo.end_date is not None and promo.end_date < today):
        return "PROMOTION_EXPIRED"
    return None


async def _coverage_limit_reason(
    db: AsyncSession, promo: Promotion, product_id: str, person_id: str
) -> str | None:
    """Cobertura del producto + límites de uso (total/por persona). Code o None. Asume la
    promo ya cargada y vigente."""
    if not promo.applies_to_all_products:
        if not await promotion_product_repository.covers_product(db, promo.id, product_id):
            return "PROMOTION_PRODUCT_NOT_COVERED"
    if promo.max_uses_total is not None:
        used_total = await promotion_usage_repository.count_for_promotion(db, promo.id)
        if used_total >= promo.max_uses_total:
            return "PROMOTION_LIMIT_REACHED"
    if promo.max_uses_per_person is not None:
        used_person = await promotion_usage_repository.count_for_promotion_person(
            db, promo.id, person_id
        )
        if used_person >= promo.max_uses_per_person:
            return "PROMOTION_PERSON_LIMIT_REACHED"
    return None


async def _ineligibility_reason(
    db: AsyncSession, promo: Promotion, product_id: str, person_id: str
) -> str | None:
    """Primer code de inelegibilidad (vigencia → cobertura → límites), o None si elegible.
    Para los read-paths (dry-run). NO chequea existencia ni no-stacking. `apply` usa
    `_promo_active_reason` + `_coverage_limit_reason` por separado para respetar el orden del
    contrato (vigencia ANTES de la existencia de product/person)."""
    return _promo_active_reason(promo) or await _coverage_limit_reason(
        db, promo, product_id, person_id
    )


async def _appointment_exists(db: AsyncSession, appointment_id: str) -> bool:
    """¿Existe la cita (viva) para el FK? Evita el IntegrityError 500 de un appointment_id
    inexistente (read directo a scheduling.appointment, sin tocar scheduling)."""
    result = await db.execute(
        select(Appointment.id).where(
            Appointment.id == appointment_id, Appointment.deleted_at.is_(None)
        )
    )
    return result.first() is not None


def _raise_ineligibility(reason: str) -> NoReturn:
    """Traduce un code de inelegibilidad a su BadRequestException (todos 400)."""
    raise BadRequestException(_INELIGIBILITY_DETAIL[reason], code=reason)


def _to_eligibility(
    promo: Promotion, base_price: Decimal, currency: str, reason: str | None
) -> PromotionEligibility:
    discount = _compute_discount(promo, base_price)
    return PromotionEligibility(
        promotion_id=promo.id,
        code=promo.code,
        name=promo.name,
        is_eligible=reason is None,
        reason=reason,
        original_amount=base_price,
        discount_amount=discount,
        final_amount=base_price - discount,
        currency=currency,
    )


# ── Denormalización del reporte de usos ──────────────────────────────────────────────


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _collect_actor_ids(rows: list[PromotionUsage]) -> set[str]:
    return {row.created_by for row in rows}


async def _product_name_map(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Batch product_id→name (read directo a catalog.Product, sin tocar catalog; mismo
    criterio que el join de promotion_product). Solo productos vivos."""
    if not ids:
        return {}
    result = await db.execute(
        select(Product.id, Product.name).where(Product.id.in_(ids), Product.deleted_at.is_(None))
    )
    return {row[0]: row[1] for row in result.all()}


def _to_item(
    usage: PromotionUsage,
    audit_users: dict[str, User],
    *,
    promotion_name: str,
    person_name: str,
    product_name: str,
    campaign_name: str | None,
) -> PromotionUsageItem:
    return PromotionUsageItem(
        id=usage.id,
        promotion_id=usage.promotion_id,
        promotion_name=promotion_name,
        person_id=usage.person_id,
        person_name=person_name,
        product_id=usage.product_id,
        product_name=product_name,
        appointment_id=usage.appointment_id,
        campaign_id=usage.campaign_id,
        campaign_name=campaign_name,
        original_amount=usage.original_amount,
        discount_amount=usage.discount_amount,
        final_amount=usage.final_amount,
        currency=usage.currency,
        notes=usage.notes,
        created_on=usage.created_on,
        created_by=usage.created_by,
        created_by_user=_audit_info(audit_users.get(usage.created_by)),
    )


async def _to_detail(db: AsyncSession, usage: PromotionUsage) -> PromotionUsageDetail:
    """Resuelve los 4 names + audit del único usage recién creado y lo arma. Un ref
    soft-deleted cae al fallback `—` (los names son convenience; el snapshot es el audit)."""
    promo_names = await promotion_repository.promotion_name_map(db, [usage.promotion_id])
    person_names = await person_option_map(db, [usage.person_id])
    product_names = await _product_name_map(db, [usage.product_id])
    campaign_names = (
        await campaign_repository.campaign_name_map(db, [usage.campaign_id])
        if usage.campaign_id is not None
        else {}
    )
    audit_users = await user_repository.get_audit_info_map(db, {usage.created_by})
    item = _to_item(
        usage,
        audit_users,
        promotion_name=promo_names.get(usage.promotion_id, "—"),
        person_name=(
            person_names[usage.person_id].full_name if usage.person_id in person_names else "—"
        ),
        product_name=product_names.get(usage.product_id, "—"),
        campaign_name=(
            campaign_names.get(usage.campaign_id) if usage.campaign_id is not None else None
        ),
    )
    return PromotionUsageDetail(**item.model_dump())


# ── Operaciones públicas ─────────────────────────────────────────────────────────────


async def apply(
    db: AsyncSession,
    *,
    promotion_id: str,
    person_id: str,
    product_id: str,
    appointment_id: str | None = None,
    campaign_id: str | None = None,
    actor_id: str,
    notes: str | None = None,
) -> SingleResponse[PromotionUsageDetail]:
    """Crea un PromotionUsage. Orden (contrato §6.3): promo → vigencia → producto → persona
    → cita(existe + no-stacking) → campaña(existe) → cobertura/límites → snapshot. NO commitea:
    cuando lo invoca scheduling.create_appointment (F4), la excepción de dominio hace rollback
    global → la cita NO se crea (atómico). Las existencias de appointment_id/campaign_id se
    validan (404) para no 500 con un FK inválido (input type-válido nunca 500)."""
    # 1) Lock de la promo (serializa el chequeo de max_uses; no-op en sqlite/smoke).
    promo = await promotion_repository.get_for_update(db, promotion_id)
    if promo is None:
        raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
    # 2) Vigencia (activa + dentro de fechas) ANTES de existencia de product/person (contrato).
    active_reason = _promo_active_reason(promo)
    if active_reason is not None:
        _raise_ineligibility(active_reason)
    # 3) Producto (base_price + currency para el snapshot).
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    # 4) Persona existe (solo se valida existencia → no se bindea el objeto, evita F841).
    if await person_repository.get_by_id(db, person_id) is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    # 5) Cita (si se provee): existe + no-stacking (el UNIQUE parcial es el backstop de carrera).
    if appointment_id is not None:
        if not await _appointment_exists(db, appointment_id):
            raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
        if await promotion_usage_repository.get_by_appointment(db, appointment_id) is not None:
            raise ConflictException(
                "Ya se aplicó una promoción a esta cita", code="PROMOTION_ALREADY_APPLIED"
            )
    # 6) Campaña (si se provee): existe (evita el IntegrityError 500 del FK).
    if campaign_id is not None:
        if await campaign_repository.get_by_id(db, campaign_id) is None:
            raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    # 7) Cobertura + límites — mismos codes que devuelven los read-paths.
    reason = await _coverage_limit_reason(db, promo, product_id, person_id)
    if reason is not None:
        _raise_ineligibility(reason)
    # 8) Cálculo (Decimal, ROUND_HALF_UP, cap a base_price) + snapshot inmutable.
    discount = _compute_discount(promo, product.base_price)
    final = product.base_price - discount
    now = utc_now()
    usage = PromotionUsage(
        id=generate_uuid(),
        promotion_id=promotion_id,
        person_id=person_id,
        product_id=product_id,
        appointment_id=appointment_id,
        campaign_id=campaign_id,
        original_amount=product.base_price,
        discount_amount=discount,
        final_amount=final,
        currency=product.currency,
        notes=notes,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    db.add(usage)
    await db.flush()
    return SingleResponse(data=await _to_detail(db, usage))


async def eligible_for(
    db: AsyncSession, *, product_id: str, person_id: str
) -> SingleResponse[list[PromotionEligibility]]:
    """Lista las promos ACTIVAS que cubren el producto, cada una evaluada (sin insertar):
    is_eligible + reason (vigencia/límites) + montos. Una promo que NO cubre el producto se
    omite (no es "inelegible", es ajena). product/person inexistentes → 404."""
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    if await person_repository.get_by_id(db, person_id) is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    promos = await promotion_repository.list_active(db)
    results: list[PromotionEligibility] = []
    for promo in promos:
        covers = promo.applies_to_all_products or await promotion_product_repository.covers_product(
            db, promo.id, product_id
        )
        if not covers:
            continue
        reason = await _ineligibility_reason(db, promo, product_id, person_id)
        results.append(_to_eligibility(promo, product.base_price, product.currency, reason))
    return SingleResponse(data=results)


async def validate(
    db: AsyncSession, *, promotion_id: str, product_id: str, person_id: str
) -> SingleResponse[PromotionEligibility]:
    """Evalúa UNA promo puntual para (product, person) sin insertar. promo/product/person
    inexistentes → 404; inelegibilidad → is_eligible=false + reason."""
    promo = await promotion_repository.get_by_id(db, promotion_id)
    if promo is None:
        raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    if await person_repository.get_by_id(db, person_id) is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    reason = await _ineligibility_reason(db, promo, product_id, person_id)
    return SingleResponse(data=_to_eligibility(promo, product.base_price, product.currency, reason))


async def compute_price(
    db: AsyncSession, *, product_id: str, person_id: str, promotion_id: str | None = None
) -> SingleResponse[ComputePriceResponse]:
    """Precio final con/sin una promo puntual. NO impone elegibilidad (decisión confirmada):
    calcula el descuento que la promo daría. product/person/promo inexistentes → 404. Sin
    promotion_id → original=final, discount=0, promotion=None."""
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    if await person_repository.get_by_id(db, person_id) is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    if promotion_id is None:
        return SingleResponse(
            data=ComputePriceResponse(
                original_amount=product.base_price,
                discount_amount=Decimal("0.00"),
                final_amount=product.base_price,
                currency=product.currency,
                promotion=None,
            )
        )
    promo = await promotion_repository.get_by_id(db, promotion_id)
    if promo is None:
        raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
    discount = _compute_discount(promo, product.base_price)
    return SingleResponse(
        data=ComputePriceResponse(
            original_amount=product.base_price,
            discount_amount=discount,
            final_amount=product.base_price - discount,
            currency=product.currency,
            promotion=PromotionOption.model_validate(promo, from_attributes=True),
        )
    )


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[PromotionUsageItem]:
    """Reporte de usos (read-only). Batch denorm de los 4 names + audit (cero N+1)."""
    items, total = await promotion_usage_repository.get_paginated(db, query_request)
    promo_names = await promotion_repository.promotion_name_map(db, [u.promotion_id for u in items])
    person_names = await person_option_map(db, [u.person_id for u in items])
    product_names = await _product_name_map(db, [u.product_id for u in items])
    campaign_names = await campaign_repository.campaign_name_map(
        db, [u.campaign_id for u in items if u.campaign_id is not None]
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[
                _to_item(
                    u,
                    audit_users,
                    promotion_name=promo_names.get(u.promotion_id, "—"),
                    person_name=(
                        person_names[u.person_id].full_name if u.person_id in person_names else "—"
                    ),
                    product_name=product_names.get(u.product_id, "—"),
                    campaign_name=(
                        campaign_names.get(u.campaign_id) if u.campaign_id is not None else None
                    ),
                )
                for u in items
            ],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )
