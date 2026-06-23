"""
GoogleCalendarAdapter sobre Google Calendar API v3 + OAuth2, vía httpx.AsyncClient
(NO el SDK sync google-api-python-client, que es bloqueante → rompería el event loop).
client_id/secret = Settings (global por entorno). Scope `calendar.readonly` (DETALLE =
sensitive → verificación OAuth de Google antes de GA). Auth con access_type=offline +
prompt=consent (para garantizar el refresh_token). ⚠ Gotcha: la app OAuth en estado
"Testing" emite refresh tokens de 7 DÍAS → publicar "In production" antes de confiar en
el almacenamiento durable.

Import LAZY de httpx dentro de cada método: el boot/smoke sin red no rompe.
F1a implementa build_auth_url/exchange_code/get_account_email/refresh/list_calendars;
`list_events` (lectura del overlay) es F2.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from app.core.config import get_settings
from app.modules.calendar.services.providers.base import (
    Credentials,
    ExternalCalendar,
)
from app.shared.utils import utc_now

_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_BASE = "https://www.googleapis.com/calendar/v3"
_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "https://www.googleapis.com/auth/calendar.readonly openid email"


class GoogleCalendarAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        self._client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET

    def build_auth_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "access_type": "offline",  # ← refresh_token
            "prompt": "consent",  # ← fuerza el refresh aun si ya consintió
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{_AUTH_BASE}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> Credentials:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()  # el caller traduce a CALENDAR_OAUTH_EXCHANGE_FAILED
            tok: dict[str, Any] = resp.json()
        return _creds_from_token(tok, fallback_refresh=None)

    async def get_account_email(self, creds: Credentials) -> str:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _USERINFO,
                headers={"Authorization": f"Bearer {creds.access_token}"},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        email = data.get("email", "")
        return str(email)

    async def refresh(self, creds: Credentials) -> Credentials:
        import httpx  # lazy

        if creds.refresh_token is None:
            # → CALENDAR_TOKEN_REFRESH_FAILED + needs_reauth en el caller.
            raise ValueError("no refresh_token")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": creds.refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()  # invalid_grant → 400 → needs_reauth
            tok: dict[str, Any] = resp.json()
        # Google NO re-emite el refresh en cada refresh → conservar el viejo.
        return _creds_from_token(
            tok, fallback_refresh=creds.refresh_token, fallback_scopes=creds.scopes
        )

    async def list_calendars(self, creds: Credentials) -> list[ExternalCalendar]:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_API_BASE}/users/me/calendarList",
                headers={"Authorization": f"Bearer {creds.access_token}"},
            )
            resp.raise_for_status()
            items: list[dict[str, Any]] = resp.json().get("items", [])
        return [
            ExternalCalendar(
                id=c["id"],
                name=c.get("summary", c["id"]),
                primary=bool(c.get("primary")),
            )
            for c in items
        ]


def _creds_from_token(
    tok: dict[str, Any],
    *,
    fallback_refresh: str | None,
    fallback_scopes: list[str] | None = None,
) -> Credentials:
    scopes = tok.get("scope", "").split() or (fallback_scopes or [])
    return Credentials(
        access_token=tok["access_token"],
        refresh_token=tok.get("refresh_token") or fallback_refresh,
        expiry=utc_now() + timedelta(seconds=int(tok.get("expires_in", 3600))),
        scopes=scopes,
    )
