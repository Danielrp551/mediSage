"""
Aggregates the catalog sub-routers under one prefix. `main.py` includes
this `router` once.
"""

from fastapi import APIRouter

from app.modules.catalog.routers.service import router as service_router
from app.modules.catalog.routers.vertical import router as vertical_router

router = APIRouter(prefix="/catalog")
router.include_router(vertical_router)
router.include_router(service_router)
# Phase 3 adds product_router.

__all__ = ["router"]
