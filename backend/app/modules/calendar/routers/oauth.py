"""
Routers del flujo OAuth. `/start` va bajo CALENDAR_CONNECTIONS_WRITE; `/callback` es
PÚBLICO (sin RBAC; gateado por el `state` firmado — la ventana OAuth no trae el bearer
del backend) y responde 302 (no JSON), molde del webhook público de conversations.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import RedirectResponse

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.calendar.schemas.connection import OAuthStartResponse
from app.modules.calendar.services import oauth as oauth_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/oauth", tags=["calendar · oauth"])

ProviderPath = Annotated[str, Path(min_length=1, description="google | microsoft")]

# Fallback del front si el state no decodificó (return_to no confiable).
_ERROR_FALLBACK = "/clinic/calendarios-externos"


@router.get(
    "/{provider}/start",
    response_model=SingleResponse[OAuthStartResponse],
    dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))],
)
async def oauth_start(
    provider: ProviderPath,
    db: DBSession,
    actor: CurrentAuth,
    return_to: Annotated[str, Query(description="URL del front a la que volver")],
) -> SingleResponse[OAuthStartResponse]:
    return await oauth_service.build_start_url(provider, actor_id=actor.id, return_to=return_to)


@router.get("/{provider}/callback", include_in_schema=False)  # PÚBLICO: sin RequirePermission
async def oauth_callback(
    provider: ProviderPath,
    db: DBSession,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> RedirectResponse:
    """Gateado por `state` (JWT firmado), NO por RBAC. Éxito → 302 al return_to; error de
    dominio → 302 con ?calendar_error=CODE (no rompe la ventana del usuario). NUNCA 5xx."""
    try:
        return_to = await oauth_service.handle_callback(db, provider, code=code, state=state)
        return RedirectResponse(url=return_to, status_code=302)
    except (BadRequestException, NotFoundException) as exc:
        code_ = exc.code or "CALENDAR_OAUTH_EXCHANGE_FAILED"
        # El return_to NO es confiable si el state no decodificó → fallback a una ruta fija.
        fallback = oauth_service.safe_return_to(state) or _ERROR_FALLBACK
        sep = "&" if "?" in fallback else "?"
        return RedirectResponse(url=f"{fallback}{sep}calendar_error={code_}", status_code=302)
