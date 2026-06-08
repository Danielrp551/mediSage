"""
Aggregator de los sub-routers de `scheduling` bajo un solo prefix (`/scheduling`).
`main.py` incluye este `router` una vez. El orden importa solo dentro de cada
sub-router (`/active` y rutas estáticas antes de `/{id}`).

F1 (este commit): solo el catálogo de estados + matriz (`/appointment-statuses/*`).
F2+ sumará availability (`/availability/*`), appointments (`/appointments/*` CRUD +
calendar + lifecycle), `/me/*` (self-service del doctor) y la facade del bot.
"""

from fastapi import APIRouter

from app.modules.scheduling.routers.appointment_status import router as status_router

router = APIRouter(prefix="/scheduling")
router.include_router(status_router)  # /appointment-statuses/* (+ matriz)

__all__ = ["router"]
