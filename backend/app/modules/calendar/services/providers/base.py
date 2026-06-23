"""
Tipos NEUTROS del adaptador de calendario (molde del ProviderResult neutro de bots).
El motor de calendar habla con estos dataclasses, no con Google/Microsoft. Todos los
datetimes son UTC-aware (los eventos del provider llegan como instantes RFC3339 con
offset → se normalizan, igual que availability.py).

La superficie de Fase 1 (F1a) son 5 métodos: build_auth_url / exchange_code /
get_account_email / refresh / list_calendars. La superficie de F2 (list_events) y la
FUTURA (get_busy/push/watch) se documentan en el Protocol comentadas para fijar el
contrato sin implementarlas (B1-B3) — así mypy --strict no exige stubearlas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class Credentials:
    """Lo que vive en Secret Manager (JSON). expiry es UTC-aware."""

    access_token: str
    refresh_token: str | None
    expiry: datetime
    scopes: list[str]


@dataclass
class ExternalCalendar:
    """Un calendario del proveedor (para la UI de mapeo)."""

    id: str  # external_calendar_id
    name: str
    primary: bool


@dataclass
class ExternalEvent:
    """Un evento leído (overlay, Fase 2). Detalle = título + horario (Q3). Instantes UTC."""

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool


class _CalendarAdapter(Protocol):
    """Contrato común de los adaptadores (GoogleCalendarAdapter / MicrosoftGraphAdapter).
    Construido con el client_id/secret del provider (Settings, global por entorno)."""

    def build_auth_url(self, *, state: str, redirect_uri: str) -> str:
        """URL de consentimiento OAuth (sin llamada de red). Incluye el `state` firmado."""
        ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> Credentials:
        """Authorization Code → tokens (Credentials). El account_email se resuelve aparte
        con get_account_email (Google lo lee de userinfo, Microsoft de /me) — así el
        contrato común queda `-> Credentials` sin tuplas."""
        ...

    async def get_account_email(self, creds: Credentials) -> str:
        """Identidad de la cuenta conectada (Google userinfo / Graph /me)."""
        ...

    async def refresh(self, creds: Credentials) -> Credentials:
        """refresh_token → nuevo access_token (+ expiry). invalid_grant → el caller marca needs_reauth."""
        ...

    async def list_calendars(self, creds: Credentials) -> list[ExternalCalendar]:
        """Los calendarios de la cuenta (para mapear a sedes)."""
        ...

    # ── Superficie F2 (lectura del overlay) ──
    async def list_events(
        self,
        creds: Credentials,
        *,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[ExternalEvent]:
        """Eventos de UN calendario en [time_min, time_max) (instantes UTC). Fase 2."""
        ...

    # ── Superficie FUTURA (documentada, NO implementada) ──
    # async def get_busy(self, creds, *, calendar_ids, time_min, time_max) -> list[tuple[datetime, datetime]]:
    #     """B1 modo BLOQUEANTE: free/busy opaco → alimenta el `busy` de compute_available_slots
    #     (extiende ADR-006). Google freebusy.query / Graph getSchedule. ⚠ getSchedule NO soporta
    #     cuentas Outlook.com personales (decisión LOCKED #6)."""
    # async def push_event(self, creds, *, calendar_id, event) -> str: ...   # B2 push (events.insert)
    # async def update_event(self, creds, *, calendar_id, external_id, event) -> None: ...  # B2
    # async def delete_event(self, creds, *, calendar_id, external_id) -> None: ...         # B2
    # async def watch(self, creds, *, calendar_id, callback_url) -> WatchChannel: ...       # B3 sync
    # async def unwatch(self, creds, *, channel) -> None: ...                               # B3
    # async def get_changes(self, creds, *, calendar_id, sync_token) -> ChangeSet: ...      # B3 delta
