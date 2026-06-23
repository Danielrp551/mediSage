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

_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_BASE = "https://www.googleapis.com/calendar/v3"
_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "https://www.googleapis.com/auth/calendar.readonly openid email"
_MAX_PAGES = 10  # cota de paginación de list_events (≤2500 eventos/calendario, anti-runaway)


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
        params: dict[str, str] = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",  # expande recurrencias a instancias concretas
            "orderBy": "startTime",
            "maxResults": "250",
        }
        url = f"{_API_BASE}/calendars/{quote(calendar_id, safe='')}/events"
        async with httpx.AsyncClient(timeout=15.0) as client:
            for _ in range(_MAX_PAGES):
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {creds.access_token}"},
                    params=params,
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                for e in data.get("items", []):
                    if e.get("status") == "cancelled":  # los cancelados no ocupan
                        continue
                    events.append(_parse_google_event(e))
                token = data.get("nextPageToken")
                if not token:
                    break
                params = {**params, "pageToken": str(token)}
        return events


def _parse_google_event(e: dict[str, Any]) -> ExternalEvent:
    start: dict[str, Any] = e.get("start", {})
    end: dict[str, Any] = e.get("end", {})
    return ExternalEvent(
        external_id=str(e.get("id", "")),
        title=str(e.get("summary") or "(sin título)"),
        starts_at=_parse_google_dt(start),
        ends_at=_parse_google_dt(end),
        all_day="date" in start,  # all-day usa `date` (sin hora); con hora usa `dateTime`
    )


def _parse_google_dt(node: dict[str, Any]) -> datetime:
    """`dateTime` (RFC3339 con offset/Z) → UTC; `date` (YYYY-MM-DD, all-day) → medianoche UTC."""
    raw = node.get("dateTime")
    if raw:
        return datetime.fromisoformat(str(raw)).astimezone(UTC)
    return datetime.fromisoformat(str(node["date"])).replace(tzinfo=UTC)


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
