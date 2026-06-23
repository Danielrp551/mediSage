"""
Factory del adaptador agnóstico (molde _PROVIDER_ADAPTERS de bots). El dict mapea el
CalendarProvider → constructor; get_adapter resuelve o lanza CALENDAR_PROVIDER_NOT_SUPPORTED.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.exceptions import BadRequestException
from app.modules.calendar.enums import CalendarProvider
from app.modules.calendar.services.providers.base import _CalendarAdapter
from app.modules.calendar.services.providers.google import GoogleCalendarAdapter
from app.modules.calendar.services.providers.microsoft import MicrosoftGraphAdapter

_CALENDAR_ADAPTERS: dict[CalendarProvider, Callable[[], _CalendarAdapter]] = {
    CalendarProvider.google: GoogleCalendarAdapter,
    CalendarProvider.microsoft: MicrosoftGraphAdapter,
    # CalendarProvider.caldav: CalDavAdapter,  # B4 diferido
}


def get_adapter(provider: str) -> _CalendarAdapter:
    try:
        key = CalendarProvider(provider)
    except ValueError as exc:
        raise BadRequestException(
            f"Proveedor de calendario no soportado: {provider!r}",
            code="CALENDAR_PROVIDER_NOT_SUPPORTED",
        ) from exc
    return _CALENDAR_ADAPTERS[key]()


__all__ = ["get_adapter"]
