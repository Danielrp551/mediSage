"""Endpoint interno del refresh del rollup (target del Cloud Scheduler). PÚBLICO (sin RBAC),
gateado por un SHARED-SECRET (hmac.compare_digest, molde bots.verify_dispatch_secret / ADR-012).
Devuelve 401 DASHBOARD_REFRESH_SECRET_INVALID si el header falta o no coincide (la spec §8 fija
401; bots usa 403 — aquí gana la spec)."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.config import get_settings
from app.core.dependencies import DBSession
from app.core.exceptions import UnauthorizedException
from app.modules.dashboards.schemas.refresh import RefreshResult
from app.modules.dashboards.services import refresh as refresh_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/internal", tags=["dashboards · internal"])

_REFRESH_SECRET_HEADER = "X-Dashboard-Refresh-Secret"


async def verify_refresh_secret(
    x_dashboard_refresh_secret: Annotated[str | None, Header(alias=_REFRESH_SECRET_HEADER)] = None,
) -> None:
    """Compara el header con DASHBOARD_REFRESH_SECRET en tiempo constante. Un secret CONFIGURADO
    vacío → 401 SIEMPRE (nunca aceptar header ausente contra secret vacío; el boot-validator ya
    impide arrancar con el módulo activo y el secret vacío fuera de dev)."""
    expected = get_settings().DASHBOARD_REFRESH_SECRET.strip()
    provided = (x_dashboard_refresh_secret or "").strip()
    if not expected or not hmac.compare_digest(provided, expected):
        raise UnauthorizedException(
            "Refresh no autorizado.", code="DASHBOARD_REFRESH_SECRET_INVALID"
        )


@router.post(
    "/refresh",
    response_model=SingleResponse[RefreshResult],
    dependencies=[Depends(verify_refresh_secret)],
)
async def refresh(db: DBSession) -> SingleResponse[RefreshResult]:
    """SIN RBAC: lo autentica el shared-secret. Recomputa el rollup (ventana móvil) y devuelve el
    RefreshResult. Un fallo de agregación → status='error' dentro del 200 (NO 5xx; degrada con
    gracia). Cloud Scheduler lo invoca cada DASHBOARD_REFRESH_INTERVAL_MINUTES."""
    return await refresh_service.run_refresh(db)
