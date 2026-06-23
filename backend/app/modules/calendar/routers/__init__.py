"""
Agrega los sub-routers de `calendar` bajo un prefijo. `main.py` incluye este `router`
una vez. El orden de declaración importa DENTRO de cada sub-router (rutas estáticas antes
de /{id}); el orden del aggregator es informativo, salvo que las rutas estáticas
(/oauth/..., /connections/list) deben quedar ANTES de /connections/{id}.

F1a: OAuth start/callback + connections (list/get/delete/calendars) + sources (PUT replace).
F2 sumará `/external-events` (la lectura del overlay) como un 4º sub-router.
"""

from fastapi import APIRouter

from app.modules.calendar.routers.connection import router as connection_router
from app.modules.calendar.routers.oauth import router as oauth_router
from app.modules.calendar.routers.source import router as source_router

router = APIRouter(prefix="/calendar")
router.include_router(oauth_router)  # /oauth/{provider}/start, /oauth/{provider}/callback
router.include_router(connection_router)  # /connections/* (incl. /{id}, /{id}/calendars)
router.include_router(source_router)  # PUT /connections/{id}/sources

__all__ = ["router"]
