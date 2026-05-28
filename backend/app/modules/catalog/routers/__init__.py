"""
Aggregates the catalog sub-routers under one prefix. `main.py` includes
this `router` once.
"""

from fastapi import APIRouter

from app.modules.catalog.routers.vertical import router as vertical_router

router = APIRouter(prefix="/catalog")
router.include_router(vertical_router)
# Phase 2 adds service_router; phase 3 adds product_router.

__all__ = ["router"]
