"""
MicrosoftGraphAdapter sobre Microsoft Graph v1.0 + OAuth2 (Entra ID), vía httpx.AsyncClient.
client_id/secret = Settings (global por entorno); tenant = Settings.MICROSOFT_OAUTH_TENANT
(default `common`). Scope `offline_access Calendars.Read User.Read`.

⚠ Outlook.com personal (decisión LOCKED #6): la LECTURA de eventos (calendarView, F2)
funciona; lo que NO soporta cuentas personales es `getSchedule` (el free/busy del modo
bloqueante futuro). Microsoft SÍ re-emite el refresh_token en cada refresh (Google NO) →
guardar el nuevo.

Import LAZY de httpx dentro de cada método: el boot/smoke sin red no rompe. F1a implementa
build_auth_url/exchange_code/get_account_email/refresh/list_calendars; `list_events` es F2.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

from app.core.config import get_settings
from app.modules.calendar.services.providers.base import (
    Credentials,
    ExternalCalendar,
    ExternalEvent,
)
from app.shared.utils import utc_now

_AUTH_BASE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_API_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = "offline_access Calendars.Read User.Read"
_MAX_PAGES = 10  # cota de paginación de list_events (@odata.nextLink, anti-runaway)


class MicrosoftGraphAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.MICROSOFT_OAUTH_CLIENT_ID
        self._client_secret = settings.MICROSOFT_OAUTH_CLIENT_SECRET
        self._tenant = settings.MICROSOFT_OAUTH_TENANT or "common"

    @property
    def _auth_url(self) -> str:
        return _AUTH_BASE.format(tenant=self._tenant)

    @property
    def _token_url(self) -> str:
        return _TOKEN_URL.format(tenant=self._tenant)

    def build_auth_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "response_mode": "query",
            "state": state,
        }
        return f"{self._auth_url}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> Credentials:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self._token_url,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "scope": _SCOPE,
                },
            )
            resp.raise_for_status()  # el caller traduce a CALENDAR_OAUTH_EXCHANGE_FAILED
            tok: dict[str, Any] = resp.json()
        return _creds_from_token(tok, fallback_refresh=None)

    async def get_account_email(self, creds: Credentials) -> str:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_API_BASE}/me",
                headers={"Authorization": f"Bearer {creds.access_token}"},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        # `mail` puede ser null en cuentas sin buzón → cae a userPrincipalName.
        email = data.get("mail") or data.get("userPrincipalName") or ""
        return str(email)

    async def refresh(self, creds: Credentials) -> Credentials:
        import httpx  # lazy

        if creds.refresh_token is None:
            # → CALENDAR_TOKEN_REFRESH_FAILED + needs_reauth en el caller.
            raise ValueError("no refresh_token")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self._token_url,
                data={
                    "refresh_token": creds.refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "scope": _SCOPE,
                },
            )
            resp.raise_for_status()  # invalid_grant → 400 → needs_reauth
            tok: dict[str, Any] = resp.json()
        # Microsoft SÍ re-emite el refresh_token → preferir el nuevo, conservar el viejo si falta.
        return _creds_from_token(
            tok, fallback_refresh=creds.refresh_token, fallback_scopes=creds.scopes
        )

    async def list_calendars(self, creds: Credentials) -> list[ExternalCalendar]:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_API_BASE}/me/calendars",
                headers={"Authorization": f"Bearer {creds.access_token}"},
            )
            resp.raise_for_status()
            items: list[dict[str, Any]] = resp.json().get("value", [])
        return [
            ExternalCalendar(
                id=c["id"],
                name=c.get("name", c["id"]),
                primary=bool(c.get("isDefaultCalendar")),
            )
            for c in items
        ]

    async def list_events(
        self,
        creds: Credentials,
        *,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[ExternalEvent]:
        import httpx  # lazy

        events: list[ExternalEvent] = []
        headers = {
            "Authorization": f"Bearer {creds.access_token}",
            "Prefer": 'outlook.timezone="UTC"',  # Graph devuelve los instantes en UTC
        }
        url = f"{_API_BASE}/me/calendars/{quote(calendar_id, safe='')}/calendarView"
        params: dict[str, str] | None = {
            "startDateTime": time_min.isoformat(),
            "endDateTime": time_max.isoformat(),
            "$top": "250",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            for _ in range(_MAX_PAGES):
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                for e in data.get("value", []):
                    if e.get("isCancelled"):  # los cancelados no ocupan (paridad con Google)
                        continue
                    events.append(_parse_ms_event(e))
                next_link = data.get("@odata.nextLink")
                if not next_link:
                    break
                url = str(next_link)  # el nextLink ya trae todos los query params
                params = None
        return events


def _parse_ms_event(e: dict[str, Any]) -> ExternalEvent:
    start: dict[str, Any] = e.get("start", {})
    end: dict[str, Any] = e.get("end", {})
    return ExternalEvent(
        external_id=str(e.get("id", "")),
        title=str(e.get("subject") or "(sin título)"),
        starts_at=_parse_graph_dt(str(start.get("dateTime", ""))),
        ends_at=_parse_graph_dt(str(end.get("dateTime", ""))),
        all_day=bool(e.get("isAllDay")),
    )


def _parse_graph_dt(value: str) -> datetime:
    """Graph (Prefer outlook.timezone=UTC) devuelve UTC SIN 'Z', con fracción de hasta 7
    dígitos → fromisoformat la rechaza. Normaliza a ≤6 dígitos y fija UTC si queda naive."""
    s = value.strip().rstrip("Z")
    if "." in s:
        head, frac = s.split(".", 1)
        frac = "".join(ch for ch in frac if ch.isdigit())[:6]
        s = f"{head}.{frac}" if frac else head
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


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
