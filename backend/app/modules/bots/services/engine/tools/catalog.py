"""
Tools MVP de solo-lectura sobre catalog (info de productos/servicios para que el bot responda).
Reusan list_active (firmas REALES verificadas):
- catalog.vertical.list_active(db) -> list[VerticalOption]
- catalog.service.list_active(db, vertical_id=None) -> list[ServiceOption]
- catalog.product.list_active(db, service_id=None) -> list[ProductOption]

⚠ `list_products_by_vertical`: el repo de catalog scopea productos por `service_id` (NO por
vertical) → la tool toma `service_id`; "por vertical" se compondría iterando los servicios del
vertical (gap anotado en F2, se resuelve si el negocio lo pide). Se registran en F2 (para
`is_registered`); el motor que las invoca llega en F3.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.catalog.services import product as catalog_product
from app.modules.catalog.services import service as catalog_service
from app.modules.catalog.services import vertical as catalog_vertical


@register_tool("list_verticals")
async def list_verticals(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    rows = await catalog_vertical.list_active(db)
    return {"verticals": [{"id": v.id, "name": v.name} for v in rows]}


@register_tool("list_services_by_vertical")
async def list_services_by_vertical(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    rows = await catalog_service.list_active(db, vertical_id=args.get("vertical_id"))
    return {"services": [{"id": s.id, "name": s.name} for s in rows]}


@register_tool("list_products_by_vertical")
async def list_products_by_vertical(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    # MVP: catalog.product.list_active scopea por service_id (ver docstring del módulo).
    rows = await catalog_product.list_active(db, service_id=args.get("service_id"))
    return {"products": [{"id": p.id, "name": p.name} for p in rows]}
