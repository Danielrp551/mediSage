"""
Agrega los sub-routers de staff bajo un solo prefix. `main.py` incluye este
`router` una sola vez (igual que clinic.routers).

F1 expone `doctor` (/doctors/*); F2 agrega `doctor_availability`
(/doctors/{id}/availability/*). El sub-router `me` (/me/*, F3) se incluye al
implementarse.
"""

from fastapi import APIRouter

from app.modules.staff.routers.doctor import router as doctor_router
from app.modules.staff.routers.doctor_availability import router as availability_router

router = APIRouter(prefix="/staff")
router.include_router(doctor_router)
router.include_router(availability_router)

__all__ = ["router"]
