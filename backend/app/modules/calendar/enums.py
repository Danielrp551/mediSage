"""
Calendar enums (value sets a nivel código, NO catálogos en BD).
- CalendarProvider: el proveedor del adaptador agnóstico (molde bots.BotProvider).
  `caldav` queda RESERVADO (3er proveedor diferido, B4) — NO seedeado ni usado en Fase 1.
- ConnectionStatus: salud de una CalendarConnection. `needs_reauth` lo setea el refresh
  cuando el provider devuelve `invalid_grant` (revocación) → la UI muestra "Reconectar".

Las columnas `calendar_connection.provider`/`.status` son `varchar` planas; Pydantic valida
contra el enum, la BD almacena el slug.
"""

from __future__ import annotations

from enum import StrEnum


class CalendarProvider(StrEnum):
    google = "google"
    microsoft = "microsoft"
    # caldav = "caldav"  # B4 diferido (Apple iCloud / Fastmail / Nextcloud) — la interfaz lo admite.


class ConnectionStatus(StrEnum):
    connected = "connected"
    needs_reauth = "needs_reauth"
    revoked = "revoked"
    error = "error"
