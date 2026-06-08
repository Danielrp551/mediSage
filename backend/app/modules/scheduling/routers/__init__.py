"""
Aggregator de los sub-routers de `scheduling` bajo un solo prefix (`/scheduling`).
`main.py` incluye este `router` una vez. El orden importa solo dentro de cada
sub-router (rutas estáticas antes de `/{id}`).

F1: catálogo de estados + matriz (`/appointment-statuses/*`).
F2: disponibilidad (`/availability/*`), citas (`/appointments/*` list+create+get) y
    self-service del doctor (`/me/appointments/list`).
F3+ sumará el lifecycle (transition/shortcuts), el calendario (`/appointments/calendar`,
    `/me/calendar`) y la facade del bot.
"""

from fastapi import APIRouter

from app.modules.scheduling.routers.appointment import router as appointment_router
from app.modules.scheduling.routers.appointment_status import router as status_router
from app.modules.scheduling.routers.availability import router as availability_router
from app.modules.scheduling.routers.me import router as me_router

router = APIRouter(prefix="/scheduling")
router.include_router(status_router)  # /appointment-statuses/* (+ matriz)
router.include_router(availability_router)  # /availability/compute, /availability/check-slot
router.include_router(appointment_router)  # /appointments/* (list + create + get)
router.include_router(me_router)  # /me/appointments/list

__all__ = ["router"]
