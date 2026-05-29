"""
Product CRUD endpoints. Permission gating via `dependencies=[...]` at the
decorator (per fastapi skill + template convention). `actor: CurrentAuth`
is requested separately when the handler needs the user id for audit columns.

`/active` accepts an optional `service_id` query param so the Products page
and downstream modules can scope the dropdown to one service. It is declared
before `/{product_id}` so the literal path isn't captured by the id route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.catalog.schemas.product import (
    ProductCreate,
    ProductDetail,
    ProductItem,
    ProductOption,
    ProductUpdate,
)
from app.modules.catalog.services import product as product_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/products", tags=["catalog · products"])


ProductIdPath = Annotated[str, Path(min_length=1, description="Product UUID")]


@router.get(
    "/active",
    response_model=list[ProductOption],
    dependencies=[Depends(RequirePermission("PRODUCTS_READ"))],
)
async def list_active_products(db: DBSession, service_id: str | None = None) -> list[ProductOption]:
    return await product_service.list_active(db, service_id=service_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[ProductItem],
    dependencies=[Depends(RequirePermission("PRODUCTS_READ"))],
)
async def list_products(query: QueryRequest, db: DBSession) -> PaginatedResponse[ProductItem]:
    return await product_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[ProductDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("PRODUCTS_CREATE"))],
)
async def create_product(
    payload: ProductCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ProductDetail]:
    return await product_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{product_id}",
    response_model=SingleResponse[ProductDetail],
    dependencies=[Depends(RequirePermission("PRODUCTS_READ"))],
)
async def get_product(product_id: ProductIdPath, db: DBSession) -> SingleResponse[ProductDetail]:
    return await product_service.get_by_id(db, product_id)


@router.put(
    "/{product_id}",
    response_model=SingleResponse[ProductDetail],
    dependencies=[Depends(RequirePermission("PRODUCTS_UPDATE"))],
)
async def update_product(
    product_id: ProductIdPath,
    payload: ProductUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ProductDetail]:
    return await product_service.update(db, product_id, payload, actor_id=actor.id)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("PRODUCTS_DELETE"))],
)
async def delete_product(product_id: ProductIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await product_service.soft_delete(db, product_id, actor_id=actor.id)
