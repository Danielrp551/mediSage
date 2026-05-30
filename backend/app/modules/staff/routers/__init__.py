"""
Agrega los sub-routers de staff bajo un solo prefix. `main.py` incluye este
`router` una sola vez (igual que clinic.routers).

F1 expone `doctor` (/doctors/*). Los sub-routers `doctor_availability`
(/doctors/{id}/availability/*, F2) y `me` (/me/*, F3) se incluyen al implementarse.
"""

from fastapi import APIRouter

from app.modules.staff.routers.doctor import router as doctor_router

router = APIRouter(prefix="/staff")
router.include_router(doctor_router)

__all__ = ["router"]
