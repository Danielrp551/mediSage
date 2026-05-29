"""
Product service. Module of functions (no classes), per template convention.
Hydrates audit users and the denormalized `service_name` + `vertical_name`
on every Item; the parent service and vertical are eager batch-loaded via a
two-level `selectinload` (never N+1).

Products are leaves of the catalog tree: their downstream dependencies
(appointments, promotions) live in other modules, so `soft_delete` has no
delete-with-children guard here. `vertical_id` is copied from the parent
service on create and never changes (both `service_id` and the service's
`vertical_id` are immutable).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.models.product import Product
from app.modules.catalog.models.service import Service
from app.modules.catalog.repositories.product import product_repository
from app.modules.catalog.repositories.service import service_repository
from app.modules.catalog.schemas.product import (
    ProductCreate,
    ProductDetail,
    ProductItem,
    ProductOption,
    ProductUpdate,
)
from app.modules.catalog.schemas.service import ServiceOption
from app.modules.catalog.schemas.vertical import VerticalOption
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


def _to_item(product: Product, audit_users: dict[str, User]) -> ProductItem:
    # `product.service` and `product.service.vertical` must be eager-loaded by
    # the caller (get_full / list load=) — both relationships are lazy="raise".
    return ProductItem(
        id=product.id,
        service_id=product.service_id,
        service_name=product.service.name,
        vertical_id=product.vertical_id,
        vertical_name=product.service.vertical.name,
        code=product.code,
        name=product.name,
        description=product.description,
        base_price=product.base_price,
        currency=product.currency,
        duration_min=product.duration_min,
        requires_appointment=product.requires_appointment,
        is_package=product.is_package,
        min_hours_to_cancel=product.min_hours_to_cancel,
        active=product.active,
        created_on=product.created_on,
        created_by=product.created_by,
        created_by_user=_audit_info(audit_users.get(product.created_by)),
        updated_on=product.updated_on,
        updated_by=product.updated_by,
        updated_by_user=_audit_info(audit_users.get(product.updated_by)),
    )


def _to_detail(product: Product, audit_users: dict[str, User]) -> ProductDetail:
    return ProductDetail(
        **_to_item(product, audit_users).model_dump(),
        service=ServiceOption.model_validate(product.service, from_attributes=True),
        vertical=VerticalOption.model_validate(product.service.vertical, from_attributes=True),
    )


def _collect_actor_ids(rows: list[Product]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def list_active(db: AsyncSession, service_id: str | None = None) -> list[ProductOption]:
    """List active products for dropdowns, optionally scoped to one service.
    Returns the raw list (no envelope), consistent with the sibling services."""
    rows = await product_repository.list_active(db, service_id=service_id)
    return [ProductOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(db: AsyncSession, product_id: str) -> SingleResponse[ProductDetail]:
    product = await product_repository.get_full(db, product_id)
    if product is None:
        raise NotFoundException("Product not found")
    audit_users = await user_repository.get_audit_info_map(
        db, {product.created_by, product.updated_by}
    )
    return SingleResponse(data=_to_detail(product, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[ProductItem]:
    items, total = await product_repository.get_paginated(
        db,
        query_request,
        load=(selectinload(Product.service).selectinload(Service.vertical),),
    )
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(p, audit_users) for p in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: ProductCreate, *, actor_id: str
) -> SingleResponse[ProductDetail]:
    service = await service_repository.get_by_id(db, payload.service_id)
    if service is None:
        raise NotFoundException("Service not found", code="SERVICE_NOT_FOUND")

    existing = await product_repository.get_by_service_and_code(
        db, payload.service_id, payload.code
    )
    if existing is not None:
        raise AlreadyExistsException(
            f"Product with code '{payload.code}' already exists in this service",
            code="PRODUCT_CODE_TAKEN",
        )

    now = utc_now()
    product = Product(
        id=generate_uuid(),
        service_id=payload.service_id,
        # Denormalized from the (immutable) parent — see Product model docstring.
        vertical_id=service.vertical_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        base_price=payload.base_price,
        currency=payload.currency,
        duration_min=payload.duration_min,
        requires_appointment=payload.requires_appointment,
        is_package=payload.is_package,
        min_hours_to_cancel=payload.min_hours_to_cancel,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await product_repository.create(db, product)

    # Reload with parents eager-loaded — `create()` refreshes only columns.
    created = await product_repository.get_full(db, product.id)
    if created is None:  # pragma: no cover - just inserted, cannot be missing
        raise NotFoundException("Product not found")
    audit_users = await user_repository.get_audit_info_map(
        db, {created.created_by, created.updated_by}
    )
    return SingleResponse(data=_to_detail(created, audit_users))


async def update(
    db: AsyncSession,
    product_id: str,
    payload: ProductUpdate,
    *,
    actor_id: str,
) -> SingleResponse[ProductDetail]:
    product = await product_repository.get_full(db, product_id)
    if product is None:
        raise NotFoundException("Product not found")

    changes = payload.model_dump(exclude_unset=True)
    # Immutable: ProductUpdate doesn't declare them. Belt-and-suspenders.
    changes.pop("code", None)
    changes.pop("service_id", None)
    changes.pop("vertical_id", None)
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()

    await product_repository.update(db, product, changes)

    refreshed = await product_repository.get_full(db, product_id)
    if refreshed is None:  # pragma: no cover - just updated, cannot be missing
        raise NotFoundException("Product not found")
    audit_users = await user_repository.get_audit_info_map(
        db, {refreshed.created_by, refreshed.updated_by}
    )
    return SingleResponse(data=_to_detail(refreshed, audit_users))


async def soft_delete(db: AsyncSession, product_id: str, *, actor_id: str) -> None:
    product = await product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Product not found")
    # No delete-with-children guard: products are leaves of the catalog tree.
    # Downstream references (appointments, promotions) live in other modules
    # and keep their FK; the soft-deleted product simply stops being bookable.
    product.updated_by = actor_id
    product.updated_on = utc_now()
    await product_repository.soft_delete(db, product)
