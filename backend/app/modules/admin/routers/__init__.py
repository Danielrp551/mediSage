"""
Aggregates the admin sub-routers under one prefix. `main.py` includes
this `router` once.
"""

from fastapi import APIRouter

from app.modules.admin.routers.auth import router as auth_router
from app.modules.admin.routers.permission import router as permission_router
from app.modules.admin.routers.role import router as role_router
from app.modules.admin.routers.user import router as user_router

router = APIRouter(prefix="/admin")
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(role_router)
router.include_router(permission_router)

__all__ = ["router"]
