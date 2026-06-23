"""
Flujo OAuth de calendar (molde: el webhook PÚBLICO de conversations + el JWT de
app.core.security). `build_start_url` firma un `state` (JWT con SECRET_KEY, exp corto);
`handle_callback` valida el state → exchange_code → secrets.put(tokens) → crea/actualiza
CalendarConnection → devuelve el return_to del front (el router hace el 302). NUNCA expone
el client_secret ni el token al browser (todo server-side, como el template).

El `state` es CSRF + anti-replay: claims actor_id/provider/nonce/return_to/exp, SIN iss/aud
(por eso jwt.decode NO pasa audience=/issuer=). El callback es PÚBLICO (sin RBAC): la ventana
OAuth no trae el bearer del backend; el gate es la firma del state.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import secrets
from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.core.security import ALGORITHM
from app.modules.calendar.enums import ConnectionStatus
from app.modules.calendar.models.calendar_connection import CalendarConnection
from app.modules.calendar.repositories.calendar_connection import (
    calendar_connection_repository,
)
from app.modules.calendar.schemas.connection import OAuthStartResponse
from app.modules.calendar.services.connection import creds_payload
from app.modules.calendar.services.providers import get_adapter
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now

_STATE_TTL = timedelta(minutes=10)  # el consentimiento OAuth es corto
_STATE_PURPOSE = "calendar_oauth"


def _redirect_uri(provider: str) -> str:
    settings = get_settings()
    base = settings.CALENDAR_OAUTH_REDIRECT_BASE.rstrip("/")
    return f"{base}/api/v1/calendar/oauth/{provider}/callback"


async def build_start_url(
    provider: str, *, actor_id: str, return_to: str
) -> SingleResponse[OAuthStartResponse]:
    adapter = get_adapter(provider)  # valida el provider (CALENDAR_PROVIDER_NOT_SUPPORTED)
    settings = get_settings()
    now = utc_now()
    state = jwt.encode(
        {
            "actor_id": actor_id,
            "provider": provider,
            "return_to": return_to,
            "nonce": generate_uuid(),
            "purpose": _STATE_PURPOSE,
            "iat": now,
            "exp": now + _STATE_TTL,
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    auth_url = adapter.build_auth_url(state=state, redirect_uri=_redirect_uri(provider))
    return SingleResponse(data=OAuthStartResponse(auth_url=auth_url))


def _decode_state(state: str, provider: str) -> dict[str, Any]:
    """Valida la firma + exp + purpose + provider del state. El state NO trae iss/aud →
    jwt.decode SIN audience=/issuer=. Cualquier fallo → CALENDAR_OAUTH_STATE_INVALID."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as exc:  # incl. ExpiredSignatureError
        raise BadRequestException(
            "State inválido o expirado", code="CALENDAR_OAUTH_STATE_INVALID"
        ) from exc
    if payload.get("purpose") != _STATE_PURPOSE or payload.get("provider") != provider:
        raise BadRequestException("State inválido", code="CALENDAR_OAUTH_STATE_INVALID")
    return payload


def safe_return_to(state: str) -> str | None:
    """Mejor-esfuerzo: extrae el return_to del state SIN levantar (para el fallback del 302
    de error del router cuando el state no decodificó). Devuelve None si no se puede."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    rt = payload.get("return_to")
    return str(rt) if isinstance(rt, str) else None


async def handle_callback(db: AsyncSession, provider: str, *, code: str, state: str) -> str:
    """Valida state → exchange → secrets.put → crea/actualiza CalendarConnection. Devuelve el
    return_to (el ROUTER hace el 302). Errores de dominio → el router los traduce a un 302
    con ?calendar_error=CODE (no rompe la ventana del usuario)."""
    payload = _decode_state(state, provider)  # CALENDAR_OAUTH_STATE_INVALID
    actor_id = str(payload["actor_id"])
    return_to = str(payload["return_to"])
    adapter = get_adapter(provider)

    try:
        creds = await adapter.exchange_code(code=code, redirect_uri=_redirect_uri(provider))
        account_email = await adapter.get_account_email(creds)
    except Exception as exc:
        raise BadRequestException(
            "No se pudo completar el OAuth", code="CALENDAR_OAUTH_EXCHANGE_FAILED"
        ) from exc

    now = utc_now()
    existing = await calendar_connection_repository.get_by_provider_email(
        db, provider, account_email
    )
    if existing is not None:
        # Reconexión: refresca el secreto + status=connected (no crea fila nueva).
        await secrets.put(existing.secret_name, creds_payload(creds))
        existing.status = ConnectionStatus.connected.value
        existing.scopes = " ".join(creds.scopes)
        existing.last_checked_at = now
        existing.last_error = None
        existing.updated_by = actor_id
        existing.updated_on = now
        await db.flush()
        return return_to

    settings = get_settings()
    conn_id = generate_uuid()
    secret_name = f"medisage-calendar-{conn_id}-{settings.ENV_NAME}"
    await secrets.put(secret_name, creds_payload(creds))  # tokens → Secret Manager
    conn = CalendarConnection(
        id=conn_id,
        provider=provider,
        account_email=account_email,
        display_name=account_email,
        secret_name=secret_name,
        status=ConnectionStatus.connected.value,
        scopes=" ".join(creds.scopes),
        last_checked_at=now,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await calendar_connection_repository.create(db, conn)
    return return_to
