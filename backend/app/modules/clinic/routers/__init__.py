"""
Aggregates the clinic sub-routers under one prefix. `main.py` includes this
`router` once.
"""

from fastapi import APIRouter

from app.modules.clinic.routers.branch import router as branch_router

router = APIRouter(prefix="/clinic")
router.include_router(branch_router)
# Phase 2 adds office_router; phases 3-4 add operating-hours + closures
# (nested under /offices/{office_id}/...).

__all__ = ["router"]
