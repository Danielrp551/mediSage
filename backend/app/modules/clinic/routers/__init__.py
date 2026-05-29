"""
Aggregates the clinic sub-routers under one prefix. `main.py` includes this
`router` once.
"""

from fastapi import APIRouter

from app.modules.clinic.routers.branch import router as branch_router
from app.modules.clinic.routers.office import router as office_router
from app.modules.clinic.routers.office_closure import router as closure_router
from app.modules.clinic.routers.office_operating_hours import router as hours_router

router = APIRouter(prefix="/clinic")
router.include_router(branch_router)
router.include_router(office_router)
# Nested under /offices/{office_id}/... : operating-hours (phase 3) + closures (phase 4).
router.include_router(hours_router)
router.include_router(closure_router)

__all__ = ["router"]
