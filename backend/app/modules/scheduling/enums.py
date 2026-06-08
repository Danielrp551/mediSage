"""
Scheduling enums (value sets a nivel código, NO catálogos en BD).
- AppointmentSource: cómo se originó la cita. Persistido como varchar(20) plano en
  appointment.source; Pydantic valida contra el enum, la BD guarda el slug.
  `bot` = creada por el bot facade (SYSTEM, F5); `advisor`/`admin` = backoffice;
  `import` = carga masiva; `api` = integración externa.
"""

from __future__ import annotations

from enum import StrEnum


class AppointmentSource(StrEnum):
    bot = "bot"
    advisor = "advisor"
    admin = "admin"
    import_ = "import"  # value = "import" (alias: `import` es palabra reservada)
    api = "api"
