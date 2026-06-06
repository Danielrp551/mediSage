# Módulo `scheduling` — Backend deep-dive

> **Última actualización**: 2026-06-06
> **Audiencia**: developer implementando `backend/app/modules/scheduling/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`ADR-006`](../../decisions/ADR-006-on-the-fly-availability.md) (disponibilidad calculada al vuelo, sin tabla de slots) + [`ADR-007`](../../decisions/ADR-007-doctor-availability-concrete-blocks.md) (la disponibilidad del doctor son BLOQUES CONCRETOS, no patrones), [`ADR-008`](../../decisions/ADR-008-configurable-transition-matrix.md) (matriz de transiciones configurable) y [`ADR-009`](../../decisions/ADR-009-forward-fk.md) (FKs forward a módulos futuros), [`_seed-and-roles.md`](../_seed-and-roles.md) (los 13 permisos `SCHEDULING` + el user/role `SYSTEM` ya canónico) y los deep-dives molde [`../crm/backend.md`](../crm/backend.md) (catálogo `code` UNIQUE + **matriz de transiciones** `is_allowed` + `history` inmutable + `transition`/`promote`) y [`../clinic/backend.md`](../clinic/backend.md) (las **fuentes de disponibilidad**: `OfficeOperatingHours` con `day_of_week` Python-weekday + `OfficeClosure` con `is_closed`) y [`../staff/backend.md`](../staff/backend.md) (`/me` self-service como molde de "Mi agenda", `DoctorAvailability` bloques concretos).

> **Contrato autoritativo**: este doc respeta la spec compartida de `scheduling` (entidades, campos, endpoints, permisos, códigos de error, fases). Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc. El overview viejo `docs/modules/scheduling.md` (plano) se porta a este molde de 4 archivos y queda **deprecado** una vez consolidado en [`README.md`](README.md).

> **Convenciones heredadas de `catalog`/`clinic`/`staff`/`crm` shipped** (repetidas aquí para que el doc se lea solo):
>
> 1. **`PUT` para updates completos** (no `PATCH`).
> 2. **`/active` para dropdowns**: devuelve **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`), igual que `catalog`/`clinic`/`staff`/`crm`.
> 3. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `AlreadyExistsException`/`ConflictException`, `BadRequestException`, `ForbiddenException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; reload-via-`get_full` tras create/update (relaciones `lazy="raise"`); `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` como whitelist estricta (los campos denormalizados NO son server-sortable/filterable — **lección hotfix `cd10c78` de `staff`**).
> 4. **Mensajes `detail` de dominio en español, `code` en inglés**; mensajes de validators Pydantic en inglés (el front re-valida con Zod). UI 100% español.
> 5. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), lista cruda en `/active`, error `{success:false, detail, code?, errors?}`.
> 6. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `scheduling` arranca en `0020` (última aplicada antes = la del módulo previo en la cadena; ver §Migrations).
> 7. Patrón **audit users**: `created_by`/`updated_by` explícitos; `*_user: UserAuditInfo | None` hidratado vía `user_repository.get_audit_info_map` batch (sin N+1).

`scheduling` es el **módulo #7** de medisage: modela las **citas** (`Appointment`) y calcula la **disponibilidad al vuelo** (ADR-006: no hay tabla de slots; el único registro persistido del calendario es `Appointment`). Cierra el flujo de negocio **lead → conversación/bot → cita → cliente**. Depende de módulos YA en prod: `crm` (`Person`, `promote_to_customer`, `LeadActivity`), `staff` (`Doctor`, `DoctorAvailability` bloques concretos), `clinic` (`Office`/`OfficeOperatingHours`/`OfficeClosure`/`Branch.timezone`/`office_vertical`), `catalog` (`Product.duration_min`, `Product.min_hours_to_cancel`, `Product.vertical_id`). Lo consume `bots` (tools `check_availability`/`book_appointment`/`cancel_appointment`).

## Estructura de archivos a crear

```
backend/app/modules/scheduling/
├── __init__.py
├── enums.py                            # AppointmentSource (bot|advisor|admin|import|api)
├── models/
│   ├── __init__.py                     # importa todos los modelos (registro en Base.metadata)
│   ├── appointment_status.py
│   ├── appointment_status_transition.py
│   ├── appointment.py
│   ├── appointment_status_history.py
│   └── appointment_change_log.py
├── schemas/
│   ├── __init__.py
│   ├── appointment_status.py           # AppointmentStatus* + StatusTransitionUpdate (+ matriz)
│   ├── appointment.py                  # Appointment* (Create/Update/Item/Detail/Option) + Transition/Reschedule/Cancel requests
│   ├── availability.py                 # AvailabilityRequest/Slot/Response + CheckSlotRequest/Response
│   └── audit.py                        # AppointmentStatusHistoryItem + AppointmentChangeLogItem + TimelineEntry
├── repositories/
│   ├── __init__.py
│   ├── appointment_status.py           # get_by_code, get_initial, count_initial, count_using_status
│   ├── appointment_status_transition.py  # is_allowed, list_outgoing, replace_outgoing
│   ├── appointment.py                  # list_overlapping (FOR UPDATE), list_in_range, calendar batch maps
│   ├── appointment_status_history.py
│   └── appointment_change_log.py
├── services/
│   ├── __init__.py
│   ├── appointment_status.py           # catálogo + matriz (1 is_initial, delete guard)
│   ├── availability.py                 # compute_available_slots (ADR-006/007) + check_slot
│   ├── appointment.py                  # 9 invariantes + create/get/list/update + reschedule + calendar
│   ├── transition.py                   # transition genérica (matriz) + shortcuts + attend→promote
│   └── bot_facade.py                   # book_from_bot / cancel_from_bot (SYSTEM)
└── routers/
    ├── __init__.py                     # aggregator: prefix="/scheduling"
    ├── appointment_status.py           # /appointment-statuses/* (+ matriz)
    ├── availability.py                 # /availability/compute, /availability/check-slot
    ├── appointment.py                  # /appointments/* (CRUD + lifecycle + calendar)
    ├── me.py                           # /me/appointments/list + /me/calendar (doctor self-service)
    └── bot_facade.py                   # /appointments/from-bot + /appointments/{id}/cancel-from-bot
```

**No hay `models/associations.py`**: `scheduling` no introduce M:N nuevas. La tabla de transición (`appointment_status_transition`) parece una asociación pero es una **entidad** (PK propia, mixins, `active`, CRUD-eable vía la matriz), igual que `crm.lead_status_transition`. Por eso va como modelo normal, no como `Table()` pura.

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean):

```python
from app.modules import admin, bots, catalog, clinic, conversations, crm, scheduling, staff  # noqa: F401
```

Y registrar el aggregator en `app/main.py` (un solo `include_router`, como `crm`/`clinic`/`staff`):

```python
from app.modules.scheduling.routers import router as scheduling_router

app.include_router(scheduling_router)  # prefix="/api/v1" + "/scheduling" interno
```

El aggregator `routers/__init__.py` replica el patrón de `crm/routers/__init__.py`:

```python
"""
Aggregates the scheduling sub-routers under one prefix. `main.py` includes este
`router` una vez. El orden importa solo dentro de cada sub-router (/active y
/calendar antes de /{id}); el orden del aggregator es informativo.
"""

from fastapi import APIRouter

from app.modules.scheduling.routers.appointment import router as appointment_router
from app.modules.scheduling.routers.appointment_status import router as status_router
from app.modules.scheduling.routers.availability import router as availability_router
from app.modules.scheduling.routers.bot_facade import router as bot_facade_router
from app.modules.scheduling.routers.me import router as me_router

router = APIRouter(prefix="/scheduling")
router.include_router(status_router)        # /appointment-statuses/* (+ matriz)
router.include_router(availability_router)  # /availability/compute, /availability/check-slot
router.include_router(appointment_router)   # /appointments/* (CRUD + lifecycle + calendar)
router.include_router(me_router)            # /me/appointments/list + /me/calendar
router.include_router(bot_facade_router)    # /appointments/from-bot + /appointments/{id}/cancel-from-bot

__all__ = ["router"]
```

> ⚠ El `bot_facade_router` también cuelga de `/appointments/...` (`/appointments/from-bot`, `/appointments/{id}/cancel-from-bot`). Para que `from-bot` no lo capture la ruta dinámica `/{id}`, los paths estáticos del `appointment_router` (`/calendar`) y los del bot facade van declarados **antes** de `/{id}` dentro de su propio router; como `from-bot` y `cancel-from-bot` viven en otro router incluido **después**, usar paths inequívocos (`from-bot` no colisiona con un UUID, pero `cancel-from-bot` sí cuelga de `/{id}/...`, lo cual es seguro porque es un segmento literal extra). Ver §Routers.

## Enums — `enums.py` (en código, NO en BD)

`AppointmentSource` es un contrato estable del código (no un catálogo en BD). La columna `appointment.source` es `varchar(20)` plana; Pydantic valida contra el enum, la BD almacena el slug.

```python
"""
Scheduling enums (code-level value sets, NO DB catalogs).
- AppointmentSource: cómo se originó la cita. Persistido como varchar(20).
  `bot` = creada por el bot facade (SYSTEM); `advisor`/`admin` = backoffice;
  `import` = carga masiva; `api` = integración externa.
"""

from __future__ import annotations

from enum import StrEnum


class AppointmentSource(StrEnum):
    bot = "bot"
    advisor = "advisor"
    admin = "admin"
    import_ = "import"  # value = "import" (alias para evitar la palabra reservada)
    api = "api"
```

> ⚠ `import` es palabra reservada en Python: el miembro se nombra `import_` con value `"import"`. **No** se puede declarar `import = "import"`. En Pydantic el campo `source: AppointmentSource` acepta el string `"import"` y resuelve a `AppointmentSource.import_`. Si se prefiere no usar el sufijo, declarar `IMPORT = "import"` (miembro en mayúsculas, value en minúsculas) — pero la convención del codebase (`crm.ChannelType`) usa lowercase, así que se mantiene `import_` con el value correcto.

## Models — SQLAlchemy 2.0

**Mixins** (de `app.shared.base_model`): `PrimaryKeyMixin` (`id`), `ActiveMixin` (`active`), `SoftDeleteMixin` (`deleted_at`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **`AppointmentStatusTransition`, `AppointmentStatusHistory` y `AppointmentChangeLog` NO llevan `SoftDeleteMixin`** — la matriz es config (deshabilitar arista = `active=false` o DELETE real) y los dos audit-trails son inmutables (append-only).

> ⚠ **Las FKs forward a tablas de otros módulos YA existen** (a diferencia de `crm`, que las dejó sin constraint): `person`, `doctor`, `office`, `branch`, `product`, `user` y `appointment_status` son tablas en prod. Por eso `Appointment` SÍ declara `ForeignKey(...)` reales hacia ellas (ADR-009 aplica solo cuando la tabla destino aún no existe; aquí todas existen). Lo que NO se declara es `relationship` ORM hacia esos modelos cross-módulo (se resuelven por id + batch maps, igual que `crm` resuelve advisor/status sin relationship). La única self-FK (`previous_appointment_id` → `appointment.id`) tampoco lleva relationship (la cadena se recorre por id si hiciera falta).

### `models/appointment_status.py` — tabla `appointment_status` (catálogo) — PK·A·SD·T

Espeja `crm.LeadStatus`. Flags que manejan el lifecycle sin hardcodear codes.

```python
"""
Catálogo configurable de estados de cita (espeja crm.LeadStatus). `code` es un
slug estable en minúsculas/dígitos/_ (validado en Pydantic+Zod). Las banderas
manejan el ciclo de vida sin hardcodear codes:
- is_initial: EXACTAMENTE UNO true (la cita nace aquí al agendar). Validado en service.
- is_final: estado terminal (ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED). NO soft-deletea la
  fila (registro histórico — diverge de crm, ver Appointment).
- is_active_attention: 0..N (puede haber varios; en la práctica solo IN_PROGRESS). Marca
  "en atención ahora" para la grilla y los reportes.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class AppointmentStatus(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "appointment_status"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # hex para badges
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

### `models/appointment_status_transition.py` — tabla `appointment_status_transition` (matriz) — PK·A·T (SIN SD)

Espeja `crm.LeadStatusTransition`. ADR-008.

```python
"""
ADR-008: una arista configurable del grafo de estados de cita (from → to). El
service valida las transiciones contra ESTA tabla (repo.is_allowed). Editable por
admin (APPOINTMENT_STATUSES_WRITE): el seed instala una matriz base que la clínica
refina. Sin SoftDeleteMixin — es config: deshabilitar una arista = active=false
(se conserva la fila) o DELETE (se elimina).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class AppointmentStatusTransition(
    PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base
):
    __tablename__ = "appointment_status_transition"
    __table_args__ = (
        UniqueConstraint(
            "from_status_id",
            "to_status_id",
            name="uq_appointment_status_transition_from_to",
        ),
    )

    from_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=False, index=True
    )
    to_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=False
    )
```

### `models/appointment.py` — tabla `appointment` — PK·A·SD·T

La unidad persistida del calendario. **NO se soft-deletea al cerrar**: los estados finales (ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED) mantienen la fila viva como registro histórico (DIVERGE de crm, donde `is_final` soft-deletea). DELETE (soft) = solo "error de captura".

```python
"""
Appointment = la unidad persistida del calendario (ADR-006: la disponibilidad NO
se persiste, se calcula al vuelo; lo único que ocupa tiempo es esta fila). Reserva
el rango [scheduled_for, scheduled_for + duration_min) para el chequeo de conflicto.

`branch_id` es DENORM de office.branch_id (copiado al agendar) — evita un join en
cada chequeo de conflicto/listado y permite el índice (branch_id, scheduled_for,
status_id). `duration_min` se COPIA de product.duration_min al agendar (fallback
doctor.slot_duration_min si NULL); es exacto, no se redondea (la grilla de slots SÍ
exige N=ceil(duration_min/slot_duration_min) slots contiguos, pero la fila guarda la
duración real).

`previous_appointment_id` es self-FK (cadena de reagendamiento, acíclica por
construcción). Todas las FKs cross-módulo son reales (las tablas existen) pero SIN
relationship ORM — se resuelven por id + batch maps (igual que crm con status/advisor).

NO se soft-deletea al cerrar: una cita ATTENDED/CANCELLED/… mantiene la fila viva
(histórico). DELETE (soft) = solo error de captura. (Diverge de crm.)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:  # pragma: no cover
    pass  # no relationship ORM hacia otros módulos


class Appointment(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "appointment"
    __table_args__ = (
        Index("ix_appointment_doctor_scheduled", "doctor_id", "scheduled_for"),
        Index("ix_appointment_office_scheduled", "office_id", "scheduled_for"),
        Index("ix_appointment_person_scheduled", "person_id", "scheduled_for"),
        Index(
            "ix_appointment_branch_scheduled_status",
            "branch_id",
            "scheduled_for",
            "status_id",
        ),
    )

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("doctor.id"), nullable=False
    )
    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("office.id"), nullable=False
    )
    # DENORM de office.branch_id (copiado al agendar; el office no se mueve de sede).
    branch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("branch.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product.id"), nullable=False
    )
    # Inicio de la cita, en UTC (timestamptz). El render local lo hace el browser.
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Copiado de product.duration_min al agendar (fallback doctor.slot_duration_min).
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=False
    )
    # AppointmentSource value (bot|advisor|admin|import|api).
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # Self-FK: cadena de reagendamiento (la cita vieja apunta a la nueva vía la
    # nueva; la NUEVA guarda el id de la vieja). Acíclica por construcción.
    previous_appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

> **Por qué `branch_id` denormalizado**: `office.branch_id` es inmutable (un office no se mueve de sede — ver `clinic`), así que copiarlo en `appointment` no genera drift. El índice `(branch_id, scheduled_for, status_id)` cubre el listado/calendario filtrado por sede + rango + estado sin tocar `office`. El invariante #1 (`office.branch_id == appointment.branch_id`) lo revalida al crear/reagendar.

### `models/appointment_status_history.py` — tabla `appointment_status_history` — PK·A·T (SIN SD)

Espeja `crm.LeadStatusHistory`. Timeline inmutable de cambios de **estado**.

```python
"""
Log inmutable de transiciones de estado de una cita (espeja crm.LeadStatusHistory).
Sin SoftDeleteMixin (audit trail honesto). from_status_id es NULL en la primera fila
(creación de la cita). changed_by es FK a user.id (NULL = bot/sistema). SIN
relationship al padre (acceso por appointment_id + batch maps). Append-only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class AppointmentStatusHistory(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "appointment_status_history"

    appointment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=False, index=True
    )
    from_status_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=True
    )
    to_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_status.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### `models/appointment_change_log.py` — tabla `appointment_change_log` — PK·A·T (SIN SD)

Cambios **in-place de columnas NO-estado** (doctor_id, office_id, notes, …). Los cambios de `status_id` van a History; `scheduled_for` NO se edita in-place (usa `/reschedule`).

```python
"""
Log inmutable de cambios in-place de columnas NO-estado de una cita (doctor_id,
office_id, notes, product_id, …). Sin SoftDeleteMixin. Los cambios de status_id NO
van acá (van a AppointmentStatusHistory); scheduled_for NO se edita in-place (eso es
/reschedule, que crea una cita nueva). previous_value/new_value se serializan a texto
(UUID/ISO8601/string) — un solo formato para cualquier columna.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class AppointmentChangeLog(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "appointment_change_log"

    appointment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(60), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### `models/__init__.py`

```python
"""
Importar los modelos acá los registra en Base.metadata antes de que Alembic lea el
esquema y antes de resolver los relationship() por string. Orden: catálogo + matriz
antes que appointment; appointment antes que sus audit-trails.
"""

from app.modules.scheduling.models.appointment_status import AppointmentStatus
from app.modules.scheduling.models.appointment_status_transition import (
    AppointmentStatusTransition,
)
from app.modules.scheduling.models.appointment import Appointment
from app.modules.scheduling.models.appointment_status_history import (
    AppointmentStatusHistory,
)
from app.modules.scheduling.models.appointment_change_log import AppointmentChangeLog

__all__ = [
    "AppointmentStatus",
    "AppointmentStatusTransition",
    "Appointment",
    "AppointmentStatusHistory",
    "AppointmentChangeLog",
]
```

**Lazy strategy**: `scheduling` no declara relationships ORM cross-módulo ni hacia la self-FK — todo se resuelve por id + batch maps en los repos (igual que `crm` resuelve `lead_status`/`advisor` sin relationship). Esto mantiene `scheduling` desacoplado y evita N+1 silencioso.

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (idénticas a [`../crm/backend.md`](../crm/backend.md#schemas-pydantic-v2--completos)):
>
> 1. **No usar Ellipsis (`...`)** en `Field(...)`. Campo sin `default=` ya es obligatorio.
> 2. **`Annotated`** solo para parámetros HTTP (`Query`, `Path`) en routers.
> 3. **Validators**: `@field_validator` single-field, `@model_validator(mode="after")` cross-field.
> 4. **Mensajes de validator en inglés** (van al detalle 422). El texto user-facing en español vive en el Zod del frontend.

### `schemas/appointment_status.py` (catálogo + matriz)

```python
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo

# Code del catálogo de estado en MAYÚSCULAS (convención de catálogos de estado; espeja
# crm.LeadStatus, que usa NUEVO/CONTACTADO/… SIN pattern). Inmutable: los shortcuts del service
# resuelven por code (get_by_code("CONFIRMED")) → renombrarlo rompería los shortcuts.
CODE_PATTERN = re.compile(r"^[A-Z0-9_]+$")


class AppointmentStatusCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool = False
    is_final: bool = False
    is_active_attention: bool = False
    display_order: int = 0

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError("code must be a lowercase slug: letters/digits/_ only")
        return v


class AppointmentStatusUpdate(BaseModel):
    """`code` es inmutable (slug estable) → no se declara."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool | None = None
    is_final: bool | None = None
    is_active_attention: bool | None = None
    display_order: int | None = None
    active: bool | None = None


class AppointmentStatusItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    is_initial: bool
    is_final: bool
    is_active_attention: bool
    display_order: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class AppointmentStatusOption(BaseModel):
    """Dropdown / badge shape — GET /appointment-statuses/active (lista cruda)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_initial: bool = False
    is_final: bool = False
    is_active_attention: bool = False


class StatusTransitionUpdate(BaseModel):
    """Body de PUT /appointment-statuses/{id}/transitions — REEMPLAZA las aristas
    de salida de un estado con exactamente estos destinos."""

    to_ids: list[str] = Field(default_factory=list)

    @field_validator("to_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("to_ids must not contain duplicates")
        return v
```

> No hay `WON_REQUIRES_FINAL` ni `is_won` (eso es de `crm`). La única validación de catálogo es **exactamente un `is_initial`** (`MULTIPLE_INITIAL_STATUS`, en el service) — `is_active_attention` es 0..N (no se valida unicidad).

### `schemas/availability.py` (request / slot / response del cómputo + check-slot)

```python
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AvailabilityRequest(BaseModel):
    """Body de POST /availability/compute. branch_id/office_id opcionales acotan
    los offices candidatos; si faltan, se consideran todos los offices aptos del
    doctor. El rango [from_date, to_date] es inclusivo."""

    doctor_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    branch_id: str | None = None
    office_id: str | None = None
    from_date: date_type
    to_date: date_type

    @model_validator(mode="after")
    def _range_ok(self) -> "AvailabilityRequest":
        if self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date")
        return self


class AvailabilitySlot(BaseModel):
    """Un slot libre concreto. starts_at/ends_at son timestamptz UTC (el browser
    los renderiza en la TZ del branch). Denormaliza doctor/office/branch para que la
    grilla/wizard no joineen."""

    model_config = ConfigDict(from_attributes=True)
    starts_at: datetime
    ends_at: datetime
    doctor_id: str
    doctor_name: str
    office_id: str
    office_name: str
    branch_id: str
    branch_name: str


class AvailabilityResponse(BaseModel):
    slots: list[AvailabilitySlot] = Field(default_factory=list)
    duration_min: int  # la duración efectiva de la cita (de product, fallback doctor)
    doctor_slot_duration_min: int  # el grano del calendario del doctor


class CheckSlotRequest(BaseModel):
    """Body de POST /availability/check-slot — revalida UN slot puntual antes de book."""

    doctor_id: str = Field(min_length=1)
    office_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    scheduled_for: datetime  # inicio propuesto, UTC


class CheckSlotResponse(BaseModel):
    available: bool
    reason: str | None = None  # code del primer invariante que falla (None si available)
```

### `schemas/appointment.py` (Appointment + requests de lifecycle)

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.scheduling.enums import AppointmentSource
from app.modules.scheduling.schemas.appointment_status import AppointmentStatusOption


class AppointmentCreate(BaseModel):
    """Body de POST /appointments (book). duration_min NO se acepta del cliente:
    se COPIA de product.duration_min (fallback doctor.slot_duration_min) en el
    service. branch_id NO se acepta: se DERIVA de office.branch_id (denorm). El
    estado nace en el is_initial."""

    person_id: str = Field(min_length=1)
    doctor_id: str = Field(min_length=1)
    office_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    scheduled_for: datetime  # inicio, UTC
    source: AppointmentSource = AppointmentSource.advisor
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    """Body de PUT /appointments/{id} — SOLO columnas no-estado y no-tiempo (cada
    cambio → AppointmentChangeLog). status_id se cambia por /transition; scheduled_for
    por /reschedule. branch_id se re-deriva si cambia office_id."""

    doctor_id: str | None = None
    office_id: str | None = None
    product_id: str | None = None
    notes: str | None = None
    reason: str | None = Field(default=None, max_length=255)  # para el changelog


class AppointmentTransitionRequest(BaseModel):
    """Body de POST /appointments/{id}/transition (genérico, valida matriz)."""

    to_status_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class AppointmentCancelRequest(BaseModel):
    """Body de POST /appointments/{id}/cancel."""

    cancellation_reason: str | None = Field(default=None, max_length=255)


class AppointmentRescheduleRequest(BaseModel):
    """Body de POST /appointments/{id}/reschedule. Crea una cita NUEVA (mismo
    person/product por defecto; doctor/office/scheduled_for nuevos) y marca la vieja
    RESCHEDULED. doctor_id/office_id opcionales = se reusan los de la cita vieja."""

    scheduled_for: datetime  # nuevo inicio, UTC
    doctor_id: str | None = None
    office_id: str | None = None
    reason: str | None = Field(default=None, max_length=255)


class AppointmentItem(BaseModel):
    """Fila de la tabla de citas. Denormaliza person/doctor/office/branch/product +
    el badge de estado para que la lista no joinee. NINGUNO de los denormalizados va
    en ALLOWED_FIELDS (lección cd10c78); el filtro por doctor/estado/sede/producto =
    deep-link query param → el repo (columnas reales: están en appointment)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    person_name: str  # denorm de crm.Person (full_name)
    doctor_id: str
    doctor_name: str  # denorm de staff.Doctor.user.full_name
    office_id: str
    office_name: str  # denorm de clinic.Office.name
    branch_id: str
    branch_name: str  # denorm de clinic.Branch.name
    product_id: str
    product_name: str  # denorm de catalog.Product.name
    scheduled_for: datetime
    duration_min: int
    status: AppointmentStatusOption  # badge (id/code/name/color/flags)
    source: AppointmentSource
    previous_appointment_id: str | None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class AppointmentDetail(AppointmentItem):
    """Detalle completo: agrega notas/cancelación/confirmación/atención + el timeline
    (status_history + change_log entrelazados, ver schemas/audit.py)."""

    notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    cancelled_by: str | None
    confirmed_at: datetime | None
    attended_at: datetime | None
    status_history: list["AppointmentStatusHistoryItem"]  # de schemas/audit.py
    change_log: list["AppointmentChangeLogItem"]          # de schemas/audit.py


class AppointmentOption(BaseModel):
    """Dropdown / referencia compacta — no hay /active de citas, pero el shape lo usan
    la cadena de reagendamiento y respuestas internas."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    scheduled_for: datetime
    doctor_name: str
    person_name: str
```

> `AppointmentDetail` referencia `AppointmentStatusHistoryItem`/`AppointmentChangeLogItem` por forward-ref string; al final del módulo `schemas/appointment.py` hacer `AppointmentDetail.model_rebuild()` tras importar ambos de `schemas/audit.py` (o declararlos en el mismo archivo). El `model_config = ConfigDict(from_attributes=True)` no aplica a `AppointmentDetail` para esos campos: el service los arma como listas explícitas (no salen de un attribute del modelo).

### `schemas/audit.py` (history + change_log + timeline entrelazado)

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.scheduling.schemas.appointment_status import AppointmentStatusOption


class AppointmentStatusHistoryItem(BaseModel):
    """Una fila del timeline de estado. from_status null en la creación. Claves
    `from_status`/`to_status` (denormalizadas a AppointmentStatusOption para el badge)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    appointment_id: str
    from_status: AppointmentStatusOption | None = None
    to_status: AppointmentStatusOption
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None


class AppointmentChangeLogItem(BaseModel):
    """Una fila del log de cambios in-place de columnas no-estado."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    appointment_id: str
    field_name: str
    previous_value: str | None
    new_value: str | None
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None


class TimelineEntry(BaseModel):
    """Entrada unificada del timeline (status_history + change_log entrelazados por
    changed_at) para que la UI de detalle dibuje un solo hilo cronológico. La UI puede
    usar AppointmentDetail.status_history/change_log por separado; este shape es opcional
    (lo arma el front o un helper del service)."""

    kind: Literal["status", "field"]
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None
    # status:
    from_status: AppointmentStatusOption | None = None
    to_status: AppointmentStatusOption | None = None
    # field:
    field_name: str | None = None
    previous_value: str | None = None
    new_value: str | None = None
```

## Repositories

`ALLOWED_FIELDS` es el whitelist de columnas filtrable/ordenable desde el frontend (ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md)). **Lección hotfix `cd10c78` de `staff`**: solo columnas **reales** de la tabla — nunca campos denormalizados. El filtro de la tabla de citas por doctor/estado/sede/producto/fecha SÍ es server-side porque `doctor_id`/`status_id`/`branch_id`/`product_id`/`scheduled_for` SON columnas reales de `appointment` (a diferencia de `crm.person`, donde `lead_status_id` vive en otra tabla). Los nombres denormalizados (`doctor_name`, `person_name`, …) NO van en `ALLOWED_FIELDS`.

### `repositories/appointment_status.py` + `appointment_status_transition.py` (catálogo + matriz)

Idénticos a `crm.lead_status` (sin `count_initial` extra de `is_won`). Reusan el patrón `is_allowed`/`list_outgoing`/`replace_outgoing`.

```python
class AppointmentStatusRepository(BaseRepository[AppointmentStatus]):
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "is_initial", "is_final", "is_active_attention",
        "display_order", "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(AppointmentStatus)

    async def get_by_code(self, db: AsyncSession, code: str) -> AppointmentStatus | None:
        result = await db.execute(
            select(AppointmentStatus).where(
                AppointmentStatus.code == code, AppointmentStatus.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def get_initial(self, db: AsyncSession) -> AppointmentStatus | None:
        """El único is_initial (NO_INITIAL_STATUS si no hay)."""
        result = await db.execute(
            select(AppointmentStatus).where(
                AppointmentStatus.is_initial.is_(True),
                AppointmentStatus.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def count_initial(self, db: AsyncSession, exclude_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(AppointmentStatus).where(
            AppointmentStatus.is_initial.is_(True), AppointmentStatus.deleted_at.is_(None)
        )
        if exclude_id is not None:
            stmt = stmt.where(AppointmentStatus.id != exclude_id)
        return (await db.execute(stmt)).scalar_one()

    async def count_using_status(self, db: AsyncSession, status_id: str) -> int:
        """Guard de DELETE (409 APPOINTMENT_STATUS_IN_USE): cuenta citas vivas en ese
        estado (el history es una traza más débil, no bloquea)."""
        result = await db.execute(
            select(func.count()).select_from(Appointment).where(
                Appointment.status_id == status_id, Appointment.deleted_at.is_(None)
            )
        )
        return result.scalar_one()

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[AppointmentStatus]:
        """Batch para denormalizar el badge de estado en los AppointmentItem."""
        if not ids:
            return []
        result = await db.execute(
            select(AppointmentStatus).where(
                AppointmentStatus.id.in_(ids), AppointmentStatus.deleted_at.is_(None)
            )
        )
        return list(result.scalars().all())
```

```python
class AppointmentStatusTransitionRepository(BaseRepository[AppointmentStatusTransition]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(AppointmentStatusTransition)

    async def is_allowed(self, db: AsyncSession, from_id: str, to_id: str) -> bool:
        """Núcleo de enforcement (ADR-008). Solo aristas activas."""
        result = await db.execute(
            select(AppointmentStatusTransition.id).where(
                AppointmentStatusTransition.from_status_id == from_id,
                AppointmentStatusTransition.to_status_id == to_id,
                AppointmentStatusTransition.active.is_(True),
            )
        )
        return result.scalars().first() is not None

    async def list_outgoing(self, db: AsyncSession, from_id: str) -> list[str]:
        """to_ids alcanzables — GET /appointment-statuses/{id}/transitions."""
        result = await db.execute(
            select(AppointmentStatusTransition.to_status_id).where(
                AppointmentStatusTransition.from_status_id == from_id,
                AppointmentStatusTransition.active.is_(True),
            )
        )
        return [row[0] for row in result.all()]

    async def replace_outgoing(self, db: AsyncSession, from_id: str) -> None:
        """PUT /transitions: borra las aristas de salida (la matriz no tiene SD;
        DELETE es real). El caller inserta el nuevo set con audit cols."""
        await db.execute(
            delete(AppointmentStatusTransition).where(
                AppointmentStatusTransition.from_status_id == from_id
            )
        )
```

### `repositories/appointment.py` — conflicto (FOR UPDATE) + rango (calendar) + batch maps

```python
class AppointmentRepository(BaseRepository[Appointment]):
    # SOLO columnas reales de `appointment`. person_name/doctor_name/office_name/
    # branch_name/product_name/status son DENORM → NO acá (lección cd10c78). Default
    # sort = scheduled_for asc.
    ALLOWED_FIELDS: set[str] = {
        "person_id", "doctor_id", "office_id", "branch_id", "product_id",
        "status_id", "source", "scheduled_for", "active", "created_on", "updated_on",
    }

    # Estados que OCUPAN tiempo del doctor/office (los finales liberados NO cuentan).
    # Se resuelven por code en el service (CANCELLED/NO_SHOW/RESCHEDULED) → ids.

    def __init__(self) -> None:
        super().__init__(Appointment)

    async def list_overlapping_for_doctor(
        self,
        db: AsyncSession,
        doctor_id: str,
        start: datetime,
        end: datetime,
        blocking_status_ids: list[str],
        exclude_id: str | None = None,
        for_update: bool = False,
    ) -> list[Appointment]:
        """Citas del doctor cuyo rango [scheduled_for, scheduled_for+duration) SOLAPA
        [start, end), en estados que ocupan tiempo. Overlap clásico: start < other_end
        AND end > other_start. El other_end se calcula con un INTERVAL desde duration_min
        (Postgres: scheduled_for + make_interval(mins => duration_min)). En sqlite (smoke)
        el solape se filtra en Python tras traer el día (ver service). for_update emite
        SELECT … FOR UPDATE (invariante #5 SLOT_TAKEN)."""
        other_end = Appointment.scheduled_for + func.make_interval(
            0, 0, 0, 0, 0, Appointment.duration_min  # years..mins → mins en la 6a pos
        )
        stmt = (
            select(Appointment)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.deleted_at.is_(None),
                Appointment.status_id.notin_(blocking_status_ids).is_(False).is_(False)
                if False else Appointment.status_id.notin_(blocking_status_ids),
                Appointment.scheduled_for < end,
                other_end > start,
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(Appointment.id != exclude_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_overlapping_for_office(
        self,
        db: AsyncSession,
        office_id: str,
        start: datetime,
        end: datetime,
        blocking_status_ids: list[str],
        exclude_id: str | None = None,
        for_update: bool = False,
    ) -> list[Appointment]:
        """Igual que el del doctor pero por office (invariante #6 OFFICE_SLOT_TAKEN)."""
        # … mismo patrón con Appointment.office_id == office_id …

    async def list_in_range(
        self,
        db: AsyncSession,
        *,
        doctor_id: str | None = None,
        office_id: str | None = None,
        branch_id: str | None = None,
        start: datetime,
        end: datetime,
        status_ids: list[str] | None = None,
    ) -> list[Appointment]:
        """Citas que SOLAPAN [start, end) para el calendario (grilla) y para el
        algoritmo de disponibilidad (resta las ocupadas del doctor). Filtra por
        doctor/office/branch/estados según se pase."""
        other_end = Appointment.scheduled_for + func.make_interval(
            0, 0, 0, 0, 0, Appointment.duration_min
        )
        stmt = select(Appointment).where(
            Appointment.deleted_at.is_(None),
            Appointment.scheduled_for < end,
            other_end > start,
        ).order_by(Appointment.scheduled_for.asc())
        if doctor_id is not None:
            stmt = stmt.where(Appointment.doctor_id == doctor_id)
        if office_id is not None:
            stmt = stmt.where(Appointment.office_id == office_id)
        if branch_id is not None:
            stmt = stmt.where(Appointment.branch_id == branch_id)
        if status_ids is not None:
            stmt = stmt.where(Appointment.status_id.in_(status_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_doctor_paginated(self, db, query_request, doctor_id):
        """/me/appointments/list — fuerza el filtro doctor_id == current.doctor.id
        sobre el QueryRequest (anti-IDOR del DOCTOR scoped a sí mismo)."""
        # añade una condición AND eq doctor_id al QueryRequest y delega en get_paginated
```

> ⚠ **`make_interval` y el smoke en sqlite**: `func.make_interval(...)` es de Postgres. El smoke corre en sqlite (aiosqlite). Para que el chequeo de conflicto funcione en ambos, el **service** trae las citas del día/rango del doctor (`list_in_range` SIN el cálculo de `other_end` en SQL — solo por `scheduled_for` en una ventana amplia) y calcula el solape en **Python** (`a.scheduled_for < end and a.scheduled_for + timedelta(minutes=a.duration_min) > start`). El `SELECT … FOR UPDATE` se aplica sobre las filas candidatas del doctor en la ventana del día (no requiere el INTERVAL en SQL). La versión SQL con `make_interval` queda como optimización Postgres-only documentada; **el path canónico es el Python-side** (lo valida el QA E2E en Postgres además del smoke). El pseudo-código del bloque de arriba (`.is_(False).is_(False)`) es un placeholder — **usar `Appointment.status_id.notin_(blocking_status_ids)`** directo.

```python
    # ── Batch maps para denormalizar AppointmentItem (sin N+1) ──
    async def person_name_map(self, db, person_ids) -> dict[str, str]: ...
    async def doctor_name_map(self, db, doctor_ids) -> dict[str, str]: ...   # join doctor→user.full_name
    async def office_map(self, db, office_ids) -> dict[str, tuple[str, str]]:  # (name, branch_id)
    async def branch_name_map(self, db, branch_ids) -> dict[str, str]: ...
    async def product_name_map(self, db, product_ids) -> dict[str, str]: ...
```

> Los batch maps siguen exactamente el patrón de `staff.doctor_availability_repository.branch_name_map`/`office_map` (una query `SELECT id, name WHERE id IN (...)`). `doctor_name_map` joinea `doctor → user` para el `full_name` (igual que `staff` resuelve el nombre del doctor). `person_name_map` lee `crm.Person` (`first_name`/`last_name` → full_name). El `status` badge se hidrata con `appointment_status_repository.get_by_ids`. Cero N+1.

### `repositories/appointment_status_history.py` + `appointment_change_log.py`

`ALLOWED_FIELDS = set()` (no hay `/list`; se leen por `appointment_id`). Cada uno expone `list_for_appointment(db, appointment_id)` ordenado por `changed_at asc` (igual que `crm.lead_status_history`). `AppointmentChangeLog` además expone `last_for_field` si hiciera falta.

## Disponibilidad — `compute_available_slots` (corazón del módulo)

`services/availability.py: compute_available_slots(db, *, doctor_id, product_id, branch_id=None, office_id=None, from_date, to_date) -> AvailabilityResponse`. **NO persiste** (ADR-006). Implementa el §3 de la spec. TZ: las horas locales de bloques/horarios se interpretan en `branch.timezone` (IANA, default `America/Lima`) y se convierten a UTC con `zoneinfo`; **el weekday se deriva EN la TZ del branch** (lección TZ recurrente: nunca derivar el día desde UTC).

### Pseudo-código detallado (ADR-007 bloques concretos + TZ + N contiguos)

```python
from datetime import datetime, timedelta, time
from math import ceil
from zoneinfo import ZoneInfo

async def compute_available_slots(db, *, doctor_id, product_id, branch_id=None,
                                  office_id=None, from_date, to_date) -> AvailabilityResponse:
    # 1) Producto → duración + vertical.
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    vertical_id = product.vertical_id  # ya denormalizado en product (no join)

    # 2) Doctor (get_full: branches + verticals, soft-deleted filtrado).
    doctor = await staff_doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    if not doctor.active:
        return AvailabilityResponse(slots=[], duration_min=..., doctor_slot_duration_min=doctor.slot_duration_min)  # decisión #3
    doctor_branch_ids = {b.id for b in doctor.branches}
    doctor_vertical_ids = {v.id for v in doctor.verticals}
    if vertical_id not in doctor_vertical_ids:
        return AvailabilityResponse(slots=[], duration_min=..., doctor_slot_duration_min=doctor.slot_duration_min)

    # 3) Grano + N contiguos.
    slot = doctor.slot_duration_min                       # grano del calendario
    duration_min = product.duration_min or doctor.slot_duration_min   # fallback
    n_contig = ceil(duration_min / slot)                  # slots contiguos requeridos

    # 4) Offices candidatos: activos, branch ∈ doctor.branches, ∩ (branch_id?/office_id?),
    #    aptos para el vertical (EXISTS office_vertical, vertical viva).
    offices = await clinic_office_repository.list_active(db, branch_id=branch_id, vertical_id=vertical_id)
    offices = [o for o in offices if o.branch_id in doctor_branch_ids]
    if office_id is not None:
        offices = [o for o in offices if o.id == office_id]
    if branch_id is not None:
        offices = [o for o in offices if o.branch_id == branch_id]
    if not offices:
        return AvailabilityResponse(slots=[], duration_min=duration_min, doctor_slot_duration_min=slot)

    # 5) Citas activas del doctor en el rango (ocupan tiempo). Resolver los estados
    #    "no bloqueantes" (CANCELLED/NO_SHOW/RESCHEDULED) a ids por code y EXCLUIRLOS.
    blocking_status_ids = await _resolve_blocking_status_ids(db)  # all - {CANCELLED,NO_SHOW,RESCHEDULED}
    range_start_utc = datetime.combine(from_date, time.min, tzinfo=ZoneInfo("UTC"))
    range_end_utc = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=ZoneInfo("UTC"))
    appts = await appointment_repository.list_in_range(
        db, doctor_id=doctor_id, start=range_start_utc, end=range_end_utc, status_ids=blocking_status_ids)
    # (status_ids = bloqueantes; o traer todas y filtrar por code en Python — ver caveat sqlite)

    # 6) Bloques disponibles del doctor en el rango (ADR-007). El repo de staff NO filtra
    #    office/branch soft-deleted → scheduling SÍ (descarta bloques cuyo office/branch murió).
    av_blocks = await doctor_availability_repository.list_for_doctor(db, doctor_id, from_date, to_date)
    av_blocks = [b for b in av_blocks if _office_alive(b.office_id, offices)]  # office candidato vivo + apto

    slots: list[AvailabilitySlot] = []
    office_by_id = {o.id: o for o in offices}

    # 7) Por cada día del rango × cada bloque de disponibilidad de ESE día/office candidato.
    for av in av_blocks:                                   # cada bloque ya trae (date, office_id, opens_at, closes_at)
        office = office_by_id.get(av.office_id)
        if office is None:                                 # bloque en un office no candidato → skip
            continue
        branch = await clinic_branch_repository.get_by_id(db, office.branch_id)
        tz = ZoneInfo(branch.timezone)                     # TZ del branch (NO del server)
        day = av.date                                      # fecha de calendario del bloque
        weekday = day.weekday()                            # 0=Lun..6=Dom EN la fecha local (correcto: date es local)

        # 7a) Intersección con OfficeOperatingHours del office para ESE weekday (varias filas/día).
        oh_rows = await office_operating_hours_repository.list_for_office(db, office.id)
        oh_today = [h for h in oh_rows if h.day_of_week == weekday]
        if not oh_today:
            continue                                       # el office no abre ese weekday → sin slots
        # ventana = ∩(bloque del doctor, unión de los OperatingHours del weekday), en time local.
        local_windows = _intersect_blocks(
            [(av.opens_at, av.closes_at)],
            [(h.opens_at, h.closes_at) for h in oh_today],
        )                                                  # lista de (open_time, close_time) locales

        # 7b) Convertir cada ventana local → UTC POR bloque (DST-safe: combine date+time en tz).
        utc_windows = []
        for (op, cl) in local_windows:
            start_local = datetime.combine(day, op, tzinfo=tz)
            end_local = datetime.combine(day, cl, tzinfo=tz)
            utc_windows.append((start_local.astimezone(ZoneInfo("UTC")),
                                end_local.astimezone(ZoneInfo("UTC"))))

        # 7c) Restar OfficeClosure is_closed=true (resta) / sumar is_closed=false (apertura extra).
        #     Los closures son timestamptz UTC → comparan directo con utc_windows.
        closures = await office_closure_repository.list_for_office(db, office.id, range_start_utc, range_end_utc)
        closed_ranges = [(c.starts_at, c.ends_at) for c in closures if c.is_closed]
        extra_open = [(c.starts_at, c.ends_at) for c in closures if not c.is_closed]
        utc_windows = _subtract_ranges(utc_windows, closed_ranges)
        utc_windows = _union_ranges(utc_windows, _clip_extra_to_day(extra_open, day, tz))  # apertura extra del día

        # 7d) Restar las citas ocupadas del doctor (rangos UTC).
        busy = [(a.scheduled_for, a.scheduled_for + timedelta(minutes=a.duration_min)) for a in appts]
        free_windows = _subtract_ranges(utc_windows, busy)

        # 7e) Generar slots de `slot` min alineados al INICIO del bloque del doctor; exigir
        #     N contiguos libres para la duración del producto.
        for (w_start, w_end) in free_windows:
            cursor = _align_to_grid(w_start, av_block_start_utc=utc_windows_origin(av, day, tz), slot)
            while cursor + timedelta(minutes=slot * n_contig) <= w_end:
                slot_start = cursor
                slot_end = cursor + timedelta(minutes=duration_min)
                # los N*slot minutos deben caber dentro de free (ya garantizado por la ventana libre)
                slots.append(AvailabilitySlot(
                    starts_at=slot_start, ends_at=slot_end,
                    doctor_id=doctor.id, doctor_name=_doctor_name(doctor),
                    office_id=office.id, office_name=office.name,
                    branch_id=branch.id, branch_name=branch.name))
                cursor = cursor + timedelta(minutes=slot)   # avanza UN grano (slots solapables cada `slot`)

    # 8) Aplanar, ordenar por starts_at, deduplicar (mismo doctor/office/start) y devolver.
    slots.sort(key=lambda s: (s.starts_at, s.office_id))
    return AvailabilityResponse(slots=_dedupe(slots), duration_min=duration_min,
                                doctor_slot_duration_min=slot)
```

Notas de implementación del algoritmo:
- **Helpers de intervalos** (`_intersect_blocks`, `_subtract_ranges`, `_union_ranges`, `_align_to_grid`): funciones puras sobre listas de `(start, end)` (time locales en 7a; datetimes UTC de 7b en adelante). Se testean en aislamiento (unit tests del service) porque son el núcleo propenso a off-by-one.
- **Weekday EN la TZ del branch**: `av.date` ya es una fecha de calendario local del bloque (el doctor agendó su disponibilidad en fechas concretas), así que `av.date.weekday()` es correcto sin conversión. El cruce con `OfficeOperatingHours.day_of_week` usa esa misma convención Python (0=Lun..6=Dom) — **idéntica a la de clinic** (NO `EXTRACT(DOW)` de Postgres). La conversión local→UTC (7b) se hace combinando `date + time` en `ZoneInfo(branch.timezone)` y luego `.astimezone(UTC)`, lo que respeta DST automáticamente.
- **Alineación de la grilla**: los slots se alinean al inicio del **bloque de disponibilidad del doctor** (no al inicio de la ventana libre tras restar citas), para que la grilla sea estable día a día. Tras restar citas, solo se emiten los slots cuyos N*slot minutos caen enteros dentro de una ventana libre.
- **N contiguos**: `n_contig = ceil(duration_min / slot)`; el slot reserva `duration_min` reales (no `n_contig*slot`), pero exige que `n_contig*slot` minutos quepan en la ventana libre alineada — así una cita de 45 min con grano 30 ocupa 2 granos (60 min de calendario) pero la fila guarda `duration_min=45`.
- **Caching**: Redis TTL 30-60s por `(doctor, from, to)` está **DIFERIDO** (MVP sin cache).
- **`_resolve_blocking_status_ids`**: trae todos los `AppointmentStatus`, mapea por code, y devuelve los ids EXCEPTO `{CANCELLED, NO_SHOW, RESCHEDULED}`. Esos tres NO ocupan tiempo (cita liberada). El resto (SCHEDULED/CONFIRMED/CHECKED_IN/IN_PROGRESS/ATTENDED) sí. (ATTENDED ocupa el slot pasado pero como el rango es futuro casi nunca importa; se incluye por consistencia.)

### `check_slot` — revalidación de UN slot puntual

`POST /availability/check-slot` lo usa el bot/asesor antes de book. Revalida los invariantes de tiempo/horario/cierre/conflicto para un único `scheduled_for`, devolviendo `{available, reason?}` sin crear nada.

```python
async def check_slot(db, *, doctor_id, office_id, product_id, scheduled_for) -> CheckSlotResponse:
    # Reusa los MISMOS helpers de validación de create_appointment (invariantes 1-8),
    # pero en modo "dry-run": en vez de lanzar, captura el primer code y lo devuelve.
    try:
        await _validate_booking_invariants(
            db, doctor_id=doctor_id, office_id=office_id, product_id=product_id,
            scheduled_for=scheduled_for, exclude_id=None, for_update=False)
        return CheckSlotResponse(available=True, reason=None)
    except (BadRequestException, ConflictException, NotFoundException) as exc:
        return CheckSlotResponse(available=False, reason=getattr(exc, "code", None))
```

> `_validate_booking_invariants` es el helper compartido por `check_slot` y `create_appointment` (DRY). En `check_slot` NO usa `FOR UPDATE` (es read-only); en `create_appointment` sí (`for_update=True`) sobre el invariante #5/#6.

## Invariantes del create/reschedule (en SERVICE, con code) — 9 + extras

Todos viven en `services/appointment.py:_validate_booking_invariants(...)`. Orden de evaluación: los baratos (existencia/branch/vertical) antes de los caros (conflicto con FOR UPDATE).

| # | Invariante | Code | HTTP |
|---|---|---|---|
| 0a | doctor `active=true` (decisión #3) | `DOCTOR_INACTIVE` | 400 |
| 1 | `office.branch_id == appointment.branch_id` | `OFFICE_NOT_IN_BRANCH` | 400 |
| 2 | `office.verticals ∋ product.vertical_id` | `OFFICE_NOT_APT_FOR_VERTICAL` | 400 |
| 3 | `branch_id ∈ doctor.branches` | `DOCTOR_NOT_IN_BRANCH` | 400 |
| 4 | `product.vertical_id ∈ doctor.verticals` | `DOCTOR_NOT_APT_FOR_VERTICAL` | 400 |
| 5 | sin conflicto de tiempo del **doctor** (SELECT FOR UPDATE) | `SLOT_TAKEN` | 409 |
| 6 | sin conflicto de tiempo del **office** | `OFFICE_SLOT_TAKEN` | 409 |
| 7 | cabe en un bloque `DoctorAvailability` del día/office | `NO_AVAILABILITY_BLOCK` | 400 |
| 8 | office abierto (en `OfficeOperatingHours`, no bloqueado por `OfficeClosure is_closed=true`) | `OFFICE_CLOSED` | 400 |
| 9 | al cancelar: `(scheduled_for - now) >= product.min_hours_to_cancel` salvo permiso override | `CANCEL_TOO_LATE` | 400 |

Extras de transición:
- transición no permitida por la matriz → `APPOINTMENT_TRANSITION_NOT_ALLOWED` (400).

```python
async def _validate_booking_invariants(db, *, doctor_id, office_id, product_id,
                                       scheduled_for, exclude_id, for_update):
    # 0) Cargar dependencias (existencia).
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None: raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    office = await clinic_office_repository.get_full(db, office_id)   # trae branch + verticals
    if office is None: raise NotFoundException("Consultorio no encontrado", code="OFFICE_NOT_FOUND")
    doctor = await staff_doctor_repository.get_full(db, doctor_id)    # trae branches + verticals
    if doctor is None: raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    branch_id = office.branch_id                                       # DENORM derivado del office

    # 0a) decisión #3 — doctor inactivo no acepta nuevas reservas.
    if not doctor.active:
        raise BadRequestException("El doctor está inactivo", code="DOCTOR_INACTIVE")
    # 1) office en el branch derivado (trivial cuando branch_id se deriva del office, pero se
    #    revalida explícito para reschedule donde el office puede cambiar).
    if office.branch_id != branch_id:
        raise BadRequestException("El consultorio no pertenece a la sede", code="OFFICE_NOT_IN_BRANCH")
    # 2) office apto para el vertical del producto.
    office_vertical_ids = {v.id for v in office.verticals}
    if product.vertical_id not in office_vertical_ids:
        raise BadRequestException("El consultorio no atiende esta vertical", code="OFFICE_NOT_APT_FOR_VERTICAL")
    # 3) doctor atiende en el branch.
    if branch_id not in {b.id for b in doctor.branches}:
        raise BadRequestException("El doctor no atiende en esta sede", code="DOCTOR_NOT_IN_BRANCH")
    # 4) doctor apto para el vertical.
    if product.vertical_id not in {v.id for v in doctor.verticals}:
        raise BadRequestException("El doctor no atiende esta vertical", code="DOCTOR_NOT_APT_FOR_VERTICAL")

    duration_min = product.duration_min or doctor.slot_duration_min
    start = scheduled_for
    end = start + timedelta(minutes=duration_min)

    # 7) cabe en un DoctorAvailability del día/office (en TZ del branch). Reusa el cómputo
    #    de ventanas locales→UTC del availability service para ESE día/office.
    if not await _fits_in_availability_block(db, doctor, office, branch_id, start, end, duration_min):
        raise BadRequestException("No hay bloque de disponibilidad", code="NO_AVAILABILITY_BLOCK")
    # 8) office abierto (OperatingHours ∋ y no OfficeClosure is_closed cubriendo el rango).
    if not await _office_open(db, office, branch_id, start, end):
        raise BadRequestException("El consultorio está cerrado", code="OFFICE_CLOSED")

    # 5) conflicto del doctor (FOR UPDATE en create). blocking_status_ids = los que ocupan tiempo.
    blocking = await _resolve_blocking_status_ids(db)
    if await _has_overlap(db, "doctor", doctor_id, start, end, blocking, exclude_id, for_update):
        raise ConflictException("El horario ya está ocupado", code="SLOT_TAKEN")
    # 6) conflicto del office.
    if await _has_overlap(db, "office", office_id, start, end, blocking, exclude_id, for_update):
        raise ConflictException("El consultorio ya está ocupado", code="OFFICE_SLOT_TAKEN")

    return _BookingContext(product=product, office=office, doctor=doctor,
                           branch_id=branch_id, duration_min=duration_min)
```

> El invariante **9 (`CANCEL_TOO_LATE`)** NO está en `_validate_booking_invariants` (es de cancelación, no de booking) — vive en el shortcut `cancel` (ver §Transiciones). `_has_overlap` trae las citas del doctor/office en una ventana del día y filtra el solape en Python (caveat sqlite del repo), con `FOR UPDATE` sobre las filas candidatas cuando `for_update=True`.

### Concurrencia — `create_appointment` con `SELECT FOR UPDATE` → `SLOT_TAKEN`

```python
async def create_appointment(db, payload: AppointmentCreate, *, actor_id) -> SingleResponse[AppointmentDetail]:
    ctx = await _validate_booking_invariants(
        db, doctor_id=payload.doctor_id, office_id=payload.office_id,
        product_id=payload.product_id, scheduled_for=payload.scheduled_for,
        exclude_id=None, for_update=True)     # ← FOR UPDATE serializa intentos concurrentes
    initial = await appointment_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException("No hay estado inicial configurado", code="NO_INITIAL_STATUS")
    now = utc_now()
    appt = Appointment(
        id=generate_uuid(), person_id=payload.person_id, doctor_id=payload.doctor_id,
        office_id=payload.office_id, branch_id=ctx.branch_id, product_id=payload.product_id,
        scheduled_for=payload.scheduled_for, duration_min=ctx.duration_min,
        status_id=initial.id, source=payload.source.value, previous_appointment_id=None,
        notes=payload.notes, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now)
    db.add(appt); await db.flush()
    # History: NULL → initial.
    db.add(AppointmentStatusHistory(
        id=generate_uuid(), appointment_id=appt.id, from_status_id=None,
        to_status_id=initial.id, changed_at=now, changed_by=actor_id, reason="Cita agendada",
        active=True, created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now))
    await db.flush()
    return SingleResponse(data=await _to_detail(db, appt))
```

> **Por qué `FOR UPDATE` previene la doble reserva**: dos `create_appointment` concurrentes sobre el mismo doctor/horario serializan en las filas candidatas del doctor (el segundo espera al commit del primero, re-evalúa el solape y detecta la cita recién creada → `SLOT_TAKEN`). La **exclusion-constraint GIST/tsrange** (que lo garantizaría a nivel BD sin FOR UPDATE) está **DIFERIDA** — el FOR UPDATE + el chequeo en Python es el mecanismo del MVP.

## Transiciones — matriz + shortcuts (services/transition.py)

`transition` genérica valida la matriz (`is_allowed`) y aplica los side-effects por estado destino (los side-effects viven acá, no en la matriz — ADR-008). Los shortcuts (`confirm`/`check-in`/`start`/`attend`/`no-show`/`cancel`/`reschedule`) resuelven el `to_status` por code y delegan en `transition`, sumando su lógica específica.

```python
async def transition(db, appointment_id, to_status_id, *, actor_id, reason=None) -> SingleResponse[AppointmentDetail]:
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    target = await appointment_status_repository.get_by_id(db, to_status_id)
    if target is None:
        raise NotFoundException("Estado no encontrado", code="APPOINTMENT_STATUS_NOT_FOUND")
    if not await appointment_status_transition_repository.is_allowed(db, appt.status_id, to_status_id):
        from_name = (await appointment_status_repository.get_by_id(db, appt.status_id)).name
        raise BadRequestException(
            f"Transición de cita no permitida: de '{from_name}' a '{target.name}'",
            code="APPOINTMENT_TRANSITION_NOT_ALLOWED")
    now = utc_now()
    from_id = appt.status_id
    # 1) History row.
    db.add(AppointmentStatusHistory(
        id=generate_uuid(), appointment_id=appt.id, from_status_id=from_id,
        to_status_id=to_status_id, changed_at=now, changed_by=actor_id, reason=reason,
        active=True, created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now))
    # 2) Aplicar el nuevo estado (la fila SIGUE viva aunque sea final — diverge de crm).
    appt.status_id = to_status_id
    appt.updated_by = actor_id; appt.updated_on = now
    # 3) Side-effects por code del destino (timestamps de columna).
    if target.code == "confirmed":
        appt.confirmed_at = now
    elif target.code == "cancelled":
        appt.cancelled_at = now; appt.cancelled_by = actor_id
    elif target.code == "attended":
        appt.attended_at = now
    await db.flush()
    return SingleResponse(data=await _to_detail(db, appt))
```

### Shortcuts (mapean a su to-state por code, vía la matriz)

| Endpoint | to_status code | Lógica extra |
|---|---|---|
| `POST /appointments/{id}/confirm` | `confirmed` | set `confirmed_at` (en `transition`) |
| `POST /appointments/{id}/check-in` | `checked_in` | — |
| `POST /appointments/{id}/start` | `in_progress` | — |
| `POST /appointments/{id}/attend` | `attended` | set `attended_at` + **attend→promote** (ver abajo) |
| `POST /appointments/{id}/no-show` | `no_show` | — |
| `POST /appointments/{id}/cancel` | `cancelled` | invariante #9 `CANCEL_TOO_LATE` + set `cancellation_reason`/`cancelled_at`/`cancelled_by` |
| `POST /appointments/{id}/reschedule` | `rescheduled` (sobre la vieja) | crea cita NUEVA + `previous_appointment_id` (ver abajo) |

```python
async def confirm(db, appointment_id, *, actor_id):
    return await _shortcut(db, appointment_id, "confirmed", actor_id=actor_id)

async def _shortcut(db, appointment_id, to_code, *, actor_id, reason=None):
    target = await appointment_status_repository.get_by_code(db, to_code)
    if target is None:
        raise BadRequestException(f"Estado '{to_code}' no configurado", code="APPOINTMENT_STATUS_NOT_FOUND")
    return await transition(db, appointment_id, target.id, actor_id=actor_id, reason=reason)
```

### `cancel` — invariante #9 (`CANCEL_TOO_LATE`) + override

```python
async def cancel(db, appointment_id, payload: AppointmentCancelRequest, *, actor: CurrentAuth):
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    product = await catalog_product_repository.get_by_id(db, appt.product_id)
    min_hours = product.min_hours_to_cancel if product else None
    if min_hours is not None:
        margin = appt.scheduled_for - utc_now()
        if margin < timedelta(hours=min_hours) and "APPOINTMENTS_CANCEL_OVERRIDE" not in actor.permissions:
            raise BadRequestException(
                f"No se puede cancelar con menos de {min_hours} h de anticipación",
                code="CANCEL_TOO_LATE")
    appt.cancellation_reason = payload.cancellation_reason
    return await _shortcut(db, appointment_id, "cancelled", actor_id=actor.id,
                           reason=payload.cancellation_reason)
```

> El permiso `APPOINTMENTS_CANCEL_OVERRIDE` se chequea **en el service** (necesita `actor.permissions`, no solo el id) — por eso `cancel` recibe `actor: CurrentAuth` completo, no solo `actor_id`. El bot facade NO hace override (corre como SYSTEM sin ese permiso → respeta `min_hours_to_cancel`).

### `reschedule` — nueva cita + `previous_appointment_id` + `exclude_id` + revalida invariantes

```python
async def reschedule(db, appointment_id, payload: AppointmentRescheduleRequest, *, actor_id):
    old = await appointment_repository.get_by_id(db, appointment_id)
    if old is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    # Solo desde {scheduled, confirmed} (la matriz lo impone: rescheduled alcanzable solo desde esos).
    new_doctor = payload.doctor_id or old.doctor_id
    new_office = payload.office_id or old.office_id
    # 1) Revalida invariantes 1-8 sobre la NUEVA cita, EXCLUYENDO la vieja del conflicto.
    ctx = await _validate_booking_invariants(
        db, doctor_id=new_doctor, office_id=new_office, product_id=old.product_id,
        scheduled_for=payload.scheduled_for, exclude_id=old.id, for_update=True)
    now = utc_now()
    # 2) Marca la vieja RESCHEDULED (vía la matriz: scheduled/confirmed → rescheduled).
    rescheduled = await appointment_status_repository.get_by_code(db, "rescheduled")
    if not await appointment_status_transition_repository.is_allowed(db, old.status_id, rescheduled.id):
        raise BadRequestException(
            "No se puede reagendar desde este estado", code="APPOINTMENT_TRANSITION_NOT_ALLOWED")
    await transition(db, old.id, rescheduled.id, actor_id=actor_id, reason=payload.reason or "Reagendada")
    # 3) Crea la NUEVA cita con previous_appointment_id = old.id, en el is_initial.
    initial = await appointment_status_repository.get_initial(db)
    new = Appointment(
        id=generate_uuid(), person_id=old.person_id, doctor_id=new_doctor, office_id=new_office,
        branch_id=ctx.branch_id, product_id=old.product_id, scheduled_for=payload.scheduled_for,
        duration_min=ctx.duration_min, status_id=initial.id, source=old.source,
        previous_appointment_id=old.id, notes=old.notes, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now)
    db.add(new); await db.flush()
    db.add(AppointmentStatusHistory(
        id=generate_uuid(), appointment_id=new.id, from_status_id=None, to_status_id=initial.id,
        changed_at=now, changed_by=actor_id, reason="Reagendada desde " + old.id, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now))
    await db.flush()
    return SingleResponse(data=await _to_detail(db, new))   # devuelve la NUEVA cita
```

Notas:
- **Todo en la MISMA transacción del request**: marcar la vieja RESCHEDULED + crear la nueva + ambos history. Si algo lanza (p.ej. el conflicto en la nueva), rollback y la vieja queda intacta.
- **`exclude_id=old.id`** evita que la cita vieja (que sigue viva en estado RESCHEDULED hasta el commit, o ya marcada) cuente como conflicto consigo misma. Además, RESCHEDULED no está en `blocking_status_ids` (no ocupa tiempo), así que aunque ya esté marcada no estorba.
- **Reschedule NO está sujeto a `min_hours_to_cancel`** (no es cancelación; el spec lo aclara).
- **Cadena acíclica por construcción**: la nueva apunta a la vieja con `previous_appointment_id`; nunca al revés. No hay ciclos.

### `attend` → `crm.promote_to_customer` + `APPOINTMENT_ATTENDED` (cross-módulo, misma tx)

```python
async def attend(db, appointment_id, *, actor_id):
    result = await _shortcut(db, appointment_id, "attended", actor_id=actor_id)  # set attended_at + history
    appt = await appointment_repository.get_by_id(db, appointment_id)
    # 1) Promote a cliente si Person aún no es cliente; si ya lo es, no-op CRM.
    existing = await crm_person_customer_status_repository.get_active_for_person(db, appt.person_id)
    if existing is None:
        try:
            await crm_person_customer_status.promote_from_lead(db, appt.person_id, actor_id=actor_id)
            # promote cierra el lead is_won (si la matriz lo permite) + crea customer is_initial.
        except ConflictException:
            pass  # carrera: ya es cliente entre el check y el promote → no-op
    # 2) Emite LeadActivity(APPOINTMENT_ATTENDED, related_appointment_id) SIEMPRE.
    await crm_lead_activity.log(
        db, appt.person_id, ActivityType.APPOINTMENT_ATTENDED,
        advisor_user_id=actor_id, actor_id=actor_id,
        content="Cita atendida", related_appointment_id=appt.id,
        payload={"appointment_id": appt.id})
    return result
```

> **Misma transacción**: el shortcut `attended` + el `promote_from_lead` + el `LeadActivity` corren en la sesión del request (commit al final). Si `promote_from_lead` falla con `NO_INITIAL_CUSTOMER_STATUS` (no hay estado cliente inicial configurado), la atención entera se revierte — es preferible no marcar ATTENDED si el promote es imposible (decisión a confirmar con el orquestador; alternativa: hacer el promote best-effort y NO revertir la atención). **Ver cross_doc_notes.** El `ActivityType.APPOINTMENT_ATTENDED` debe agregarse al enum de `crm` (cross-módulo §9).

## Bot facade — `services/bot_facade.py` (SYSTEM, sin CurrentAuth)

`book_from_bot` / `cancel_from_bot` corren como SYSTEM (`created_by = SYSTEM_USER_ID`, `source='bot'`), respetan **TODOS** los invariantes (incluido `min_hours_to_cancel` — el bot NO hace override), y emiten `LeadActivity` (`APPOINTMENT_BOOKED`/`APPOINTMENT_CANCELLED`, `related_appointment_id`). Reschedule por bot = cancel+book (sin 4ta tool en MVP).

```python
SYSTEM_USER_ID = crm_person.SYSTEM_USER_ID  # "00000000-0000-0000-0000-000000000002"

async def book_from_bot(db, ctx: BotInvocationContext, *, doctor_id, office_id, product_id,
                        scheduled_for, person_id=None) -> SingleResponse[AppointmentDetail]:
    pid = person_id or ctx.person_id
    if pid is None:
        raise BadRequestException("Falta el contacto", code="PERSON_REQUIRED")
    payload = AppointmentCreate(
        person_id=pid, doctor_id=doctor_id, office_id=office_id, product_id=product_id,
        scheduled_for=scheduled_for, source=AppointmentSource.bot, notes=None)
    result = await create_appointment(db, payload, actor_id=SYSTEM_USER_ID)  # respeta los 9 invariantes
    appt = result.data
    await crm_lead_activity.log(
        db, pid, ActivityType.APPOINTMENT_BOOKED, advisor_user_id=None, actor_id=SYSTEM_USER_ID,
        content="Cita agendada por el bot", related_appointment_id=appt.id,
        related_conversation_id=ctx.conversation_id,
        payload={"source": "bot", "appointment_id": appt.id})
    return result

async def cancel_from_bot(db, ctx: BotInvocationContext, appointment_id) -> SingleResponse[AppointmentDetail]:
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    # El bot NO tiene APPOINTMENTS_CANCEL_OVERRIDE → respeta min_hours_to_cancel.
    product = await catalog_product_repository.get_by_id(db, appt.product_id)
    if product and product.min_hours_to_cancel is not None:
        if (appt.scheduled_for - utc_now()) < timedelta(hours=product.min_hours_to_cancel):
            raise BadRequestException("Muy tarde para cancelar", code="CANCEL_TOO_LATE")
    cancelled = await appointment_status_repository.get_by_code(db, "cancelled")
    result = await transition(db, appointment_id, cancelled.id, actor_id=SYSTEM_USER_ID,
                              reason="Cancelada por el bot")
    await crm_lead_activity.log(
        db, appt.person_id, ActivityType.APPOINTMENT_CANCELLED, advisor_user_id=None,
        actor_id=SYSTEM_USER_ID, content="Cita cancelada por el bot",
        related_appointment_id=appt.id, related_conversation_id=ctx.conversation_id,
        payload={"source": "bot", "appointment_id": appt.id})
    return result
```

> `BotInvocationContext` se importa de `app.modules.bots.services.engine.tools` (`conversation_id`, `person_id`, `bot_tool_call_id`, `bot_configuration_id`). Los endpoints `/appointments/from-bot` y `/appointments/{id}/cancel-from-bot` reciben un `BotInvocationContext` en el body (sin RBAC; los protege la red interna / OIDC del dispatch de bots, igual que el resto de la superficie SYSTEM). Ver §Bot tools cross-módulo (F5).

## API contracts

Envelopes del template (idénticos a [`../crm/backend.md`](../crm/backend.md#api-contracts)):
- **Single**: `{ "success": true, "data": <T> }`
- **Paginated**: `{ "success": true, "data": { "items": [...], "total": N, "skip": 0, "limit": 10 } }`
- **Lista cruda** (`/active`): el body es directamente `[...]`.
- **Error**: `{ "success": false, "detail": "...", "code"?: "...", "errors"?: [...] }`

Prefijo común: `/api/v1/scheduling/`. Listados paginados con `POST /<recurso>/list` + `QueryRequest`. `PUT` (no `PATCH`); `/active` y `/calendar` antes de `/{id}` en el router.

### AppointmentStatus (catálogo + matriz)

#### `POST /api/v1/scheduling/appointment-statuses/list` — `APPOINTMENT_STATUSES_READ` → `PaginatedResponse[AppointmentStatusItem]`
#### `POST /api/v1/scheduling/appointment-statuses` — `APPOINTMENT_STATUSES_WRITE` → `201 SingleResponse[AppointmentStatusItem]`

**Error 409** (`code` duplicado):
```json
{ "success": false, "detail": "Ya existe un estado de cita con el código 'scheduled'", "code": "APPOINTMENT_STATUS_CODE_TAKEN" }
```

**Error 400** (segundo `is_initial`):
```json
{ "success": false, "detail": "Ya existe un estado inicial; solo puede haber uno", "code": "MULTIPLE_INITIAL_STATUS" }
```

#### `PUT /api/v1/scheduling/appointment-statuses/{id}` — `APPOINTMENT_STATUSES_WRITE` → `SingleResponse[AppointmentStatusItem]`

`code` inmutable. Re-valida `MULTIPLE_INITIAL_STATUS` sobre el merge.

#### `DELETE /api/v1/scheduling/appointment-statuses/{id}` — `APPOINTMENT_STATUSES_WRITE` → `204`

**Error 409** (en uso):
```json
{ "success": false, "detail": "No se puede eliminar: hay citas en este estado", "code": "APPOINTMENT_STATUS_IN_USE" }
```
**Error 404** → `APPOINTMENT_STATUS_NOT_FOUND`.

#### `GET /api/v1/scheduling/appointment-statuses/active` — `APPOINTMENT_STATUSES_READ` → lista cruda `list[AppointmentStatusOption]`
```json
[
  { "id": "st1...", "code": "scheduled", "name": "Agendada", "color": "#3B82F6", "is_initial": true, "is_final": false, "is_active_attention": false },
  { "id": "st4...", "code": "in_progress", "name": "En atención", "color": "#8B5CF6", "is_initial": false, "is_final": false, "is_active_attention": true }
]
```

#### `GET /api/v1/scheduling/appointment-statuses/{id}/transitions` — `APPOINTMENT_STATUSES_READ` → `SingleResponse[list[AppointmentStatusOption]]`

Los estados a los que puede ir desde `{id}` (resuelve `to_ids`). Vacío si terminal.

#### `PUT /api/v1/scheduling/appointment-statuses/{id}/transitions` — `APPOINTMENT_STATUSES_WRITE` → `SingleResponse[list[AppointmentStatusOption]]`

**Request** (`StatusTransitionUpdate`): reemplaza las aristas de salida.
```json
{ "to_ids": ["st2...", "st6...", "st7..."] }
```

### Availability

#### `POST /api/v1/scheduling/availability/compute` — `APPOINTMENTS_READ` → `SingleResponse[AvailabilityResponse]`

**Request** (`AvailabilityRequest`):
```json
{
  "doctor_id": "d1...",
  "product_id": "pr1...",
  "branch_id": "b1...",
  "office_id": null,
  "from_date": "2026-06-08",
  "to_date": "2026-06-12"
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "slots": [
      {
        "starts_at": "2026-06-08T13:00:00+00:00",
        "ends_at": "2026-06-08T13:45:00+00:00",
        "doctor_id": "d1...", "doctor_name": "Dra. Ana Torres",
        "office_id": "o1...", "office_name": "Consultorio 3 — Dental",
        "branch_id": "b1...", "branch_name": "Sede Lima Centro"
      }
    ],
    "duration_min": 45,
    "doctor_slot_duration_min": 30
  }
}
```

> `starts_at`/`ends_at` en UTC; el browser los renderiza en `branch.timezone`. Si el doctor está inactivo / no cubre el vertical / no hay offices aptos → `slots: []` (no error).

#### `POST /api/v1/scheduling/availability/check-slot` — `APPOINTMENTS_READ` → `SingleResponse[CheckSlotResponse]`

**Request** (`CheckSlotRequest`):
```json
{ "doctor_id": "d1...", "office_id": "o1...", "product_id": "pr1...", "scheduled_for": "2026-06-08T13:00:00Z" }
```

**Response** (slot libre):
```json
{ "success": true, "data": { "available": true, "reason": null } }
```
**Response** (slot ocupado):
```json
{ "success": true, "data": { "available": false, "reason": "SLOT_TAKEN" } }
```

### Appointment

#### `POST /api/v1/scheduling/appointments/list` — `APPOINTMENTS_READ` → `PaginatedResponse[AppointmentItem]`

**Request** (`QueryRequest` + deep-link query params):
```json
{ "pagination": { "skip": 0, "limit": 10 },
  "sorting": { "sort_by": "scheduled_for", "sort_order": "asc" },
  "filters": { "filters": [ { "operator": "AND", "conditions": [
    { "field": "doctor_id", "operator": "eq", "value": "d1..." },
    { "field": "status_id", "operator": "eq", "value": "st1..." }
  ] } ] } }
```
> A diferencia de `crm.persons`, los filtros por doctor/estado/sede/producto/fecha SÍ van en `conditions` (son columnas reales de `appointment`, en `ALLOWED_FIELDS`). El deep-link de la UI los traduce a `conditions`.

#### `POST /api/v1/scheduling/appointments` — `APPOINTMENTS_CREATE` → `201 SingleResponse[AppointmentDetail]`

**Request** (`AppointmentCreate`):
```json
{ "person_id": "p1...", "doctor_id": "d1...", "office_id": "o1...", "product_id": "pr1...",
  "scheduled_for": "2026-06-08T13:00:00Z", "source": "advisor", "notes": "Primera consulta" }
```

**Response 201** `SingleResponse[AppointmentDetail]` (estado = is_initial; `branch_id` derivado de office; `duration_min` copiado de product).

**Errores** (uno por invariante):
```json
{ "success": false, "detail": "El doctor está inactivo", "code": "DOCTOR_INACTIVE" }
{ "success": false, "detail": "El consultorio no pertenece a la sede", "code": "OFFICE_NOT_IN_BRANCH" }
{ "success": false, "detail": "El consultorio no atiende esta vertical", "code": "OFFICE_NOT_APT_FOR_VERTICAL" }
{ "success": false, "detail": "El doctor no atiende en esta sede", "code": "DOCTOR_NOT_IN_BRANCH" }
{ "success": false, "detail": "El doctor no atiende esta vertical", "code": "DOCTOR_NOT_APT_FOR_VERTICAL" }
{ "success": false, "detail": "No hay bloque de disponibilidad", "code": "NO_AVAILABILITY_BLOCK" }
{ "success": false, "detail": "El consultorio está cerrado", "code": "OFFICE_CLOSED" }
{ "success": false, "detail": "El horario ya está ocupado", "code": "SLOT_TAKEN" }
{ "success": false, "detail": "El consultorio ya está ocupado", "code": "OFFICE_SLOT_TAKEN" }
{ "success": false, "detail": "No hay estado inicial configurado", "code": "NO_INITIAL_STATUS" }
```

#### `GET /api/v1/scheduling/appointments/{id}` — `APPOINTMENTS_READ` → `SingleResponse[AppointmentDetail]`

Incluye `status_history` + `change_log`.
**Error 404** → `APPOINTMENT_NOT_FOUND`.

#### `PUT /api/v1/scheduling/appointments/{id}` — `APPOINTMENTS_UPDATE` → `SingleResponse[AppointmentDetail]`

Edita SOLO columnas no-estado/no-tiempo (`doctor_id`/`office_id`/`product_id`/`notes`). Cada cambio → `AppointmentChangeLog`. Si cambia `office_id`, se re-deriva `branch_id` y se revalidan invariantes 1-8 sobre el nuevo (sin tocar `scheduled_for`). `status_id`/`scheduled_for` NO son editables acá.

#### `GET /api/v1/scheduling/appointments/calendar?from=&to=&doctor_id=&office_id=&branch_id=` — `APPOINTMENTS_READ` → `SingleResponse[CalendarResponse]`

Citas (bloques sólidos por estado) + slots libres (overlay) en el rango, para la grilla. `from`/`to` ISO 8601 (obligatorios). `doctor_id`/`office_id`/`branch_id` opcionales acotan.
```json
{ "success": true, "data": {
  "appointments": [ { "id": "a1...", "scheduled_for": "...", "duration_min": 45, "status": {"...":"..."}, "doctor_name": "...", "person_name": "...", "office_name": "..." } ],
  "free_slots": [ { "starts_at": "...", "ends_at": "...", "doctor_id": "...", "office_id": "..." } ]
} }
```
> `free_slots` se computa con `compute_available_slots` cuando `doctor_id` + `product_id` vienen; si no, el calendario muestra solo `appointments` (la grilla pide los libres bajo demanda al abrir el wizard). `CalendarResponse` es un schema de `schemas/availability.py` o `schemas/appointment.py` (ver cross_doc_notes).

#### Lifecycle (transition + shortcuts)

| Endpoint | Permiso | Body | Code de error específico |
|---|---|---|---|
| `POST /appointments/{id}/transition` | `APPOINTMENTS_TRANSITION` | `AppointmentTransitionRequest` | `APPOINTMENT_TRANSITION_NOT_ALLOWED` |
| `POST /appointments/{id}/confirm` | `APPOINTMENTS_TRANSITION` | — | idem |
| `POST /appointments/{id}/check-in` | `APPOINTMENTS_TRANSITION` | — | idem |
| `POST /appointments/{id}/start` | `APPOINTMENTS_TRANSITION` | — | idem |
| `POST /appointments/{id}/attend` | `APPOINTMENTS_TRANSITION` | — | idem (+ promote cross-módulo) |
| `POST /appointments/{id}/no-show` | `APPOINTMENTS_TRANSITION` | — | idem |
| `POST /appointments/{id}/cancel` | `APPOINTMENTS_CANCEL` | `AppointmentCancelRequest` | `CANCEL_TOO_LATE` |
| `POST /appointments/{id}/reschedule` | `APPOINTMENTS_RESCHEDULE` | `AppointmentRescheduleRequest` | invariantes 1-8 + `APPOINTMENT_TRANSITION_NOT_ALLOWED` |

Todos devuelven `SingleResponse[AppointmentDetail]` (reschedule devuelve la NUEVA cita).

**Transición no permitida**:
```json
{ "success": false, "detail": "Transición de cita no permitida: de 'Agendada' a 'Atendida'", "code": "APPOINTMENT_TRANSITION_NOT_ALLOWED" }
```
**Cancelación tardía**:
```json
{ "success": false, "detail": "No se puede cancelar con menos de 24 h de anticipación", "code": "CANCEL_TOO_LATE" }
```

### Me (doctor self-service)

#### `POST /api/v1/scheduling/me/appointments/list` — `MY_APPOINTMENTS_READ` → `PaginatedResponse[AppointmentItem]`

Filtra `doctor_id == current.doctor.id` (resuelto desde `CurrentAuth` → `staff.Doctor` del user). Body = `QueryRequest`.

#### `GET /api/v1/scheduling/me/calendar?from=&to=` — `MY_APPOINTMENTS_READ` → `SingleResponse[CalendarResponse]`

La agenda del doctor logueado (sus citas en el rango). Read-only (la grilla del doctor no abre wizard).

> **Scoping anti-IDOR**: el DOCTOR con `APPOINTMENTS_READ` global ve todas las citas; el DOCTOR con solo `MY_APPOINTMENTS_READ` (sin `APPOINTMENTS_READ`) ve solo las suyas. El service de `/appointments/list` y `/appointments/{id}` aplica el filtro `doctor_id == current.doctor.id` cuando el actor tiene solo `MY_*` (espeja `_assert_can_access` de `conversations`). Resolver `current.doctor.id` requiere un lookup `staff.doctor_repository.get_by_user_id(current.user.id)` — si el user no tiene perfil Doctor y solo tiene `MY_*`, devuelve vacío / 403.

### Bot facade (sin RBAC, SYSTEM)

#### `POST /api/v1/scheduling/appointments/from-bot` → `201 SingleResponse[AppointmentDetail]`

**Request**:
```json
{ "ctx": { "conversation_id": "c1...", "person_id": "p1...", "bot_tool_call_id": "tc1..." },
  "doctor_id": "d1...", "office_id": "o1...", "product_id": "pr1...", "scheduled_for": "2026-06-08T13:00:00Z" }
```
Respeta los 9 invariantes (incl. min_hours_to_cancel en cancel-from-bot). Emite `LeadActivity(APPOINTMENT_BOOKED)`.

#### `POST /api/v1/scheduling/appointments/{id}/cancel-from-bot` → `SingleResponse[AppointmentDetail]`

**Request**: `{ "ctx": { "conversation_id": "c1...", "person_id": "p1...", "bot_tool_call_id": "tc1..." } }`. Respeta `min_hours_to_cancel` (el bot NO hace override → `CANCEL_TOO_LATE` si aplica). Emite `LeadActivity(APPOINTMENT_CANCELLED)`.

## Routers — ejemplos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; `actor: CurrentAuth` aparte cuando se necesita el id (o los permisos, como `cancel`) para audit/override; `/active` y `/calendar` antes de `/{id}`.

```python
# routers/appointment.py (extracto)
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.scheduling.schemas.appointment import (
    AppointmentCancelRequest, AppointmentCreate, AppointmentDetail, AppointmentItem,
    AppointmentRescheduleRequest, AppointmentTransitionRequest, AppointmentUpdate,
)
from app.modules.scheduling.services import appointment as appt_service
from app.modules.scheduling.services import transition as transition_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/appointments", tags=["scheduling · appointments"])

ApptIdPath = Annotated[str, Path(min_length=1, description="Appointment UUID")]


@router.get("/calendar", response_model=SingleResponse[...],
            dependencies=[Depends(RequirePermission("APPOINTMENTS_READ"))])
async def get_calendar(
    db: DBSession,
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
    doctor_id: Annotated[str | None, Query()] = None,
    office_id: Annotated[str | None, Query()] = None,
    branch_id: Annotated[str | None, Query()] = None,
) -> SingleResponse[...]:
    return await appt_service.calendar(db, from_, to, doctor_id, office_id, branch_id)


@router.post("/list", response_model=PaginatedResponse[AppointmentItem],
             dependencies=[Depends(RequirePermission("APPOINTMENTS_READ"))])
async def list_appointments(query: QueryRequest, db: DBSession, actor: CurrentAuth) -> PaginatedResponse[AppointmentItem]:
    return await appt_service.list_paginated(db, query, actor=actor)  # scoping anti-IDOR adentro


@router.post("", response_model=SingleResponse[AppointmentDetail], status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(RequirePermission("APPOINTMENTS_CREATE"))])
async def create_appointment(payload: AppointmentCreate, db: DBSession, actor: CurrentAuth) -> SingleResponse[AppointmentDetail]:
    return await appt_service.create_appointment(db, payload, actor_id=actor.id)


@router.get("/{appointment_id}", response_model=SingleResponse[AppointmentDetail],
            dependencies=[Depends(RequirePermission("APPOINTMENTS_READ"))])
async def get_appointment(appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth) -> SingleResponse[AppointmentDetail]:
    return await appt_service.get_by_id(db, appointment_id, actor=actor)


@router.post("/{appointment_id}/cancel", response_model=SingleResponse[AppointmentDetail],
             dependencies=[Depends(RequirePermission("APPOINTMENTS_CANCEL"))])
async def cancel_appointment(appointment_id: ApptIdPath, payload: AppointmentCancelRequest,
                             db: DBSession, actor: CurrentAuth) -> SingleResponse[AppointmentDetail]:
    return await transition_service.cancel(db, appointment_id, payload, actor=actor)  # actor completo (override)


@router.post("/{appointment_id}/attend", response_model=SingleResponse[AppointmentDetail],
             dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))])
async def attend_appointment(appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth) -> SingleResponse[AppointmentDetail]:
    return await transition_service.attend(db, appointment_id, actor_id=actor.id)
```

```python
# routers/me.py
me_router = APIRouter(prefix="/me", tags=["scheduling · me"])

@me_router.post("/appointments/list", response_model=PaginatedResponse[AppointmentItem],
                dependencies=[Depends(RequirePermission("MY_APPOINTMENTS_READ"))])
async def list_my_appointments(query: QueryRequest, db: DBSession, auth: CurrentAuth) -> PaginatedResponse[AppointmentItem]:
    return await appt_service.list_for_current_doctor(db, query, auth=auth)
```

```python
# routers/bot_facade.py — sin RequirePermission (SYSTEM); protegido por la red interna/OIDC
router = APIRouter(prefix="/appointments", tags=["scheduling · bot facade"])

@router.post("/from-bot", response_model=SingleResponse[AppointmentDetail], status_code=status.HTTP_201_CREATED)
async def book_from_bot(payload: BotBookRequest, db: DBSession) -> SingleResponse[AppointmentDetail]:
    return await bot_facade.book_from_bot(db, payload.ctx, doctor_id=payload.doctor_id, ...)
```

> El `Query(alias="from")` evita la palabra reservada `from` (mismo truco que `clinic.list_closures`). El `me_router` y el `bot_facade_router` se exportan e incluyen en el aggregator; `/me/appointments/list` resuelve el doctor desde `CurrentAuth`.

## Lógica adicional importante

### Denormalización sin N+1 (batch maps)

`appointments.list_paginated` hace `get_paginated` + lookups batch por `IN (ids)`: `person_name_map`, `doctor_name_map`, `office_map` (name + branch_id), `branch_name_map`, `product_name_map`, `appointment_status_repository.get_by_ids` (badge de estado) + `get_audit_info_map(created_by/updated_by/changed_by/cancelled_by)`. Cero N+1 (patrón idéntico a `staff`/`crm`). `_to_item` recibe esos maps como kwargs. `AppointmentDetail` agrega `status_history`/`change_log` resueltos vía `list_for_appointment` + sus propios badge maps.

### `update` con changelog (columnas no-estado)

```python
async def update(db, appointment_id, payload: AppointmentUpdate, *, actor_id):
    appt = await appointment_repository.get_by_id(db, appointment_id)
    if appt is None:
        raise NotFoundException("Cita no encontrada", code="APPOINTMENT_NOT_FOUND")
    now = utc_now()
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    # Si cambia office_id → re-derivar branch_id y revalidar invariantes 1-8 sobre el nuevo.
    if "office_id" in changes or "doctor_id" in changes or "product_id" in changes:
        ctx = await _validate_booking_invariants(
            db, doctor_id=changes.get("doctor_id", appt.doctor_id),
            office_id=changes.get("office_id", appt.office_id),
            product_id=changes.get("product_id", appt.product_id),
            scheduled_for=appt.scheduled_for, exclude_id=appt.id, for_update=True)
        if "office_id" in changes:
            changes["branch_id"] = ctx.branch_id  # re-derivar denorm
    for field, new_value in changes.items():
        old_value = getattr(appt, field)
        if old_value == new_value:
            continue
        db.add(AppointmentChangeLog(
            id=generate_uuid(), appointment_id=appt.id, field_name=field,
            previous_value=_serialize(old_value), new_value=_serialize(new_value),
            changed_at=now, changed_by=actor_id, reason=payload.reason, active=True,
            created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now))
        setattr(appt, field, new_value)
    appt.updated_by = actor_id; appt.updated_on = now
    await db.flush()
    return SingleResponse(data=await _to_detail(db, appt))
```

> `_serialize(value)` convierte el valor a texto: UUID/str directo, datetime → ISO8601, None → None. El `change_log` registra `branch_id` re-derivado como un cambio más (traza honesta).

### Audit columns con `created_by` / `updated_by`

Cada service que persiste recibe `actor_id` explícito desde el router (`actor: CurrentAuth`). El bot facade usa el `SYSTEM` user (`00000000-0000-0000-0000-000000000002`) como `created_by`/`actor_id`. `changed_by`/`cancelled_by` NULL o SYSTEM cuando son automáticos.

### `BaseRepository` filtra `deleted_at IS NULL`

Igual que el resto: en `get_by_id`/`get_paginated` no repetir el filtro; en queries custom (`get_by_code`, `list_in_range`, `list_overlapping_*`, batch maps) sí agregarlo explícito. Recordar: una cita CANCELLED/ATTENDED sigue VIVA (`deleted_at IS NULL`) — solo el "error de captura" la soft-deletea.

## Migrations

Migraciones **manuales y numeradas** (convención medisage). `scheduling` arranca en `0020` (la última aplicada antes de scheduling es la del módulo previo en la cadena — `bots`/`conversations`; el `down_revision` de `0020` es esa revisión). **Revision id ≤ 32 chars**. Las FKs cross-módulo SON reales (las tablas existen) — NO son forward sin constraint. La self-FK de `appointment` se agrega al final (FK circular evitada: appointment se referencia a sí misma, lo cual SQLAlchemy/Postgres resuelven con la FK inline porque la tabla ya existe al momento del ADD).

### `0020_scheduling_status.py` (F1 — appointment_status + matriz) · revid `0020_scheduling_status` (22 chars)

```sql
CREATE TABLE appointment_status (
    id                  VARCHAR(36) PRIMARY KEY,
    code                VARCHAR(40)  NOT NULL UNIQUE,
    name                VARCHAR(120) NOT NULL,
    description         TEXT,
    color               VARCHAR(20),
    is_initial          BOOLEAN NOT NULL DEFAULT FALSE,
    is_final            BOOLEAN NOT NULL DEFAULT FALSE,
    is_active_attention BOOLEAN NOT NULL DEFAULT FALSE,
    display_order       INTEGER NOT NULL DEFAULT 0,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);

-- Matriz de transiciones (ADR-008). Sin deleted_at (config; active conmuta).
CREATE TABLE appointment_status_transition (
    id             VARCHAR(36) PRIMARY KEY,
    from_status_id VARCHAR(36) NOT NULL REFERENCES appointment_status(id),
    to_status_id   VARCHAR(36) NOT NULL REFERENCES appointment_status(id),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL,
    CONSTRAINT uq_appointment_status_transition_from_to UNIQUE (from_status_id, to_status_id)
);
CREATE INDEX ix_appointment_status_transition_from ON appointment_status_transition (from_status_id);
-- revision = "0020_scheduling_status"
-- down_revision = "0019_bots_engine_state"  (última migración aplicada; verificado en alembic/versions/)
```

### `0021_scheduling_appointment.py` (F2 — appointment + status_history + change_log) · revid `0021_scheduling_appointment` (27 chars)

```sql
CREATE TABLE appointment (
    id                      VARCHAR(36) PRIMARY KEY,
    person_id               VARCHAR(36) NOT NULL REFERENCES person(id),
    doctor_id               VARCHAR(36) NOT NULL REFERENCES doctor(id),
    office_id               VARCHAR(36) NOT NULL REFERENCES office(id),
    branch_id               VARCHAR(36) NOT NULL REFERENCES branch(id),       -- DENORM de office.branch_id
    product_id              VARCHAR(36) NOT NULL REFERENCES product(id),
    scheduled_for           TIMESTAMPTZ NOT NULL,
    duration_min            INTEGER NOT NULL,
    status_id               VARCHAR(36) NOT NULL REFERENCES appointment_status(id),
    source                  VARCHAR(20) NOT NULL,
    previous_appointment_id VARCHAR(36) REFERENCES appointment(id),           -- self-FK (cadena reagendamiento)
    notes                   TEXT,
    cancellation_reason     VARCHAR(255),
    cancelled_at            TIMESTAMPTZ,
    cancelled_by            VARCHAR(36) REFERENCES "user"(id),
    confirmed_at            TIMESTAMPTZ,
    attended_at             TIMESTAMPTZ,
    active                  BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_appointment_doctor_scheduled         ON appointment (doctor_id, scheduled_for);
CREATE INDEX ix_appointment_office_scheduled         ON appointment (office_id, scheduled_for);
CREATE INDEX ix_appointment_person_scheduled         ON appointment (person_id, scheduled_for);
CREATE INDEX ix_appointment_branch_scheduled_status  ON appointment (branch_id, scheduled_for, status_id);

CREATE TABLE appointment_status_history (   -- NO deleted_at (inmutable)
    id             VARCHAR(36) PRIMARY KEY,
    appointment_id VARCHAR(36) NOT NULL REFERENCES appointment(id),
    from_status_id VARCHAR(36) REFERENCES appointment_status(id),
    to_status_id   VARCHAR(36) NOT NULL REFERENCES appointment_status(id),
    changed_at     TIMESTAMPTZ NOT NULL,
    changed_by     VARCHAR(36) REFERENCES "user"(id),
    reason         VARCHAR(255),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_appointment_status_history_appointment ON appointment_status_history (appointment_id);

CREATE TABLE appointment_change_log (       -- NO deleted_at (inmutable)
    id             VARCHAR(36) PRIMARY KEY,
    appointment_id VARCHAR(36) NOT NULL REFERENCES appointment(id),
    field_name     VARCHAR(60) NOT NULL,
    previous_value TEXT,
    new_value      TEXT,
    changed_at     TIMESTAMPTZ NOT NULL,
    changed_by     VARCHAR(36) REFERENCES "user"(id),
    reason         VARCHAR(255),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_appointment_change_log_appointment ON appointment_change_log (appointment_id);
-- revision = "0021_scheduling_appointment"
-- down_revision = "0020_scheduling_status"
```

> `"user"` entre comillas (palabra reservada en Postgres). La **self-FK** `previous_appointment_id → appointment(id)` se puede declarar inline (la tabla ya existe en el momento del `CREATE`/`ADD`) — a diferencia de la FK circular de `bots` (config↔version), aquí la referencia es a la MISMA tabla, lo que Postgres acepta inline. F0, F3, F4 y F5 NO llevan migración (F0 = solo seed/skeleton; F3 = lifecycle sobre tablas ya creadas; F4 = calendar es read; F5 = bot facade reusa lo existente).

**Cadena de revids** (ambos ≤32): `0020_scheduling_status` (22) → `0021_scheduling_appointment` (27).

## Seed

Los **13 permisos** de `scheduling` se consolidan en [`_seed-and-roles.md`](../_seed-and-roles.md) (`module="SCHEDULING"`): `MENU-SCHEDULING`, `APPOINTMENT_STATUSES_READ/WRITE`, `APPOINTMENTS_READ/CREATE/UPDATE/TRANSITION/CANCEL/RESCHEDULE/CANCEL_OVERRIDE`, `MY_APPOINTMENTS_READ`, `APPOINTMENTS_READ`. Agregarlos a `SEED_PERMISSIONS` y a los subsets de rol vía el helper `_seed_role` (idempotente, filtra por código):

- **ADMIN**: todos los 13.
- **ASESOR**: `MENU-SCHEDULING` + `APPOINTMENT_STATUSES_READ` + `APPOINTMENTS_READ/CREATE/UPDATE/TRANSITION/CANCEL/RESCHEDULE` + `APPOINTMENTS_READ` (NO `CANCEL_OVERRIDE`, NO `STATUSES_WRITE`, NO `MY_*`).
- **DOCTOR**: `MENU-SCHEDULING` + `APPOINTMENTS_READ` (scoped a sí mismo vía service) + `APPOINTMENTS_TRANSITION` (su agenda) + `MY_APPOINTMENTS_READ` + `APPOINTMENTS_READ`.

### `_seed_appointment_statuses` (8) — idempotente (por `code`)

```python
APPOINTMENT_STATUS_SEED: list[tuple] = [
    # (code, name, color, is_initial, is_final, is_active_attention, display_order)
    ("SCHEDULED",   "Agendada",     "#3B82F6", True,  False, False, 10),
    ("CONFIRMED",   "Confirmada",   "#06B6D4", False, False, False, 20),
    ("CHECKED_IN",  "En recepción", "#F59E0B", False, False, False, 30),
    ("IN_PROGRESS", "En atención",  "#8B5CF6", False, False, True,  40),
    ("ATTENDED",    "Atendida",     "#22C55E", False, True,  False, 50),
    ("NO_SHOW",     "No asistió",   "#EF4444", False, True,  False, 60),
    ("CANCELLED",   "Cancelada",    "#6B7280", False, True,  False, 70),
    ("RESCHEDULED", "Reagendada",   "#9CA3AF", False, True,  False, 80),
]
```

> `is_initial` único = `SCHEDULED`. `is_final` = {`ATTENDED`, `NO_SHOW`, `CANCELLED`, `RESCHEDULED`}. `is_active_attention` único = `IN_PROGRESS`. Los `code` en **MAYÚSCULAS sin pattern slug** (espeja crm.LeadStatus: NUEVO/CONTACTADO/…); los shortcuts del service resuelven por estos codes (`get_by_code("CONFIRMED")`, etc.) — **renombrar un code rompería los shortcuts**, por eso `code` es inmutable.

### `_seed_appointment_transition_matrix` — matriz base (la clínica la refina)

Tras seedear los estados, insertar las aristas base (resolviendo `code` → `id`). Idempotente: solo crea aristas faltantes.

```python
APPOINTMENT_TRANSITIONS: list[tuple[str, str]] = [
    ("scheduled",  "confirmed"), ("scheduled",  "checked_in"), ("scheduled",  "no_show"),
    ("scheduled",  "cancelled"), ("scheduled",  "rescheduled"),
    ("confirmed",  "checked_in"), ("confirmed",  "no_show"), ("confirmed",  "cancelled"),
    ("confirmed",  "rescheduled"),
    ("checked_in", "in_progress"), ("checked_in", "cancelled"),
    ("in_progress", "attended"), ("in_progress", "cancelled"),
    # Finales (attended/no_show/cancelled/rescheduled) sin salida.
]
```

> Reschedule permitido desde {`scheduled`, `confirmed`} (las únicas aristas hacia `rescheduled`). El resto de shortcuts mapean a su to-state por la matriz. La clínica puede ampliarla por la UI.

## Cambios cross-módulo (aditivos)

### 1) `crm.enums.ActivityType += APPOINTMENT_ATTENDED`

El enum ya tiene `APPOINTMENT_BOOKED` y `APPOINTMENT_CANCELLED`; falta `APPOINTMENT_ATTENDED` (para el `attend→promote`). Cambio aditivo de una línea:

```python
# crm/enums.py — dentro de class ActivityType(StrEnum):
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"      # ya existe
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"  # ya existe
    APPOINTMENT_ATTENDED = "APPOINTMENT_ATTENDED"    # NUEVO (scheduling F3)
```

> ⚠ **El enum es `StrEnum`** (no `str, Enum`) en el código real — usar la misma base. Es persistido como `varchar(40)` plano, así que agregar un miembro no requiere migración. `crm.lead_activity.log` ya acepta `related_appointment_id` (verificado: el modelo `LeadActivity` lo tiene como columna forward, índice, sin constraint — y `scheduling` NO agrega la FK constraint en MVP; el `related_appointment_id` queda como columna libre, igual que hoy). **Si se desea, scheduling puede agregar la FK constraint `lead_activity.related_appointment_id → appointment.id` de forma aditiva (ADR-009), pero NO es necesario en MVP** — ver cross_doc_notes.

### 2) `attend` → `crm.promote_to_customer` (ver §Transiciones)

Si `Person` no tiene `PersonCustomerStatus` activo → `crm.person_customer_status.promote_from_lead` (cierra lead is_won + crea customer is_initial); si ya es cliente → no-op CRM. Siempre emite `LeadActivity(APPOINTMENT_ATTENDED, related_appointment_id)`. Misma transacción.

### 3) `bots/services/engine/tools/scheduling.py` nuevo (fase final, F5)

Registrar 3 tools en el `TOOL_REGISTRY` de bots (sin migración). Indexadas por `code`. Pasan de `TOOL_NOT_REGISTERED` a operativas. Reusa el patrón verificado de `bots/services/engine/tools/crm.py` (`@register_tool` + `BotInvocationContext` + corren como SYSTEM, capturan la excepción y la reportan como result al LLM en vez de romper el turno):

```python
# backend/app/modules/bots/services/engine/tools/scheduling.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.scheduling.services import availability as sched_availability
from app.modules.scheduling.services import bot_facade as sched_bot


@register_tool("check_availability")
async def check_availability(args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession) -> dict[str, Any]:
    """Lista slots libres para (doctor, product, rango). → /availability/compute."""
    resp = await sched_availability.compute_available_slots(
        db, doctor_id=args["doctor_id"], product_id=args["product_id"],
        branch_id=args.get("branch_id"), office_id=args.get("office_id"),
        from_date=datetime.fromisoformat(args["from_date"]).date(),
        to_date=datetime.fromisoformat(args["to_date"]).date())
    return {"slots": [s.model_dump(mode="json") for s in resp.slots[:20]],
            "duration_min": resp.duration_min}


@register_tool("book_appointment")
async def book_appointment(args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession) -> dict[str, Any]:
    """Reserva una cita como SYSTEM. → bot_facade.book_from_bot. Captura el code del invariante."""
    try:
        result = await sched_bot.book_from_bot(
            db, ctx, doctor_id=args["doctor_id"], office_id=args["office_id"],
            product_id=args["product_id"], scheduled_for=datetime.fromisoformat(args["scheduled_for"]),
            person_id=args.get("person_id"))
        return {"ok": True, "appointment_id": result.data.id}
    except Exception as exc:  # noqa: BLE001 — invariante → reportar al LLM, no romper el turno
        return {"ok": False, "error": getattr(exc, "code", None) or str(exc)[:255]}


@register_tool("cancel_appointment")
async def cancel_appointment(args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession) -> dict[str, Any]:
    """Cancela una cita como SYSTEM (respeta min_hours_to_cancel). → bot_facade.cancel_from_bot."""
    try:
        await sched_bot.cancel_from_bot(db, ctx, args["appointment_id"])
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": getattr(exc, "code", None) or str(exc)[:255]}
```

> Reschedule por bot = `cancel_appointment` + `book_appointment` (sin 4ta tool en MVP, decisión #4). Las 3 tools se registran al importar el módulo (el motor las invoca en runtime). Hay que **importar** `app.modules.bots.services.engine.tools.scheduling` en el `tools/__init__.py` de bots (o donde se haga el import de `crm`/`catalog`) para que el `@register_tool` corra al boot.

## Checklist de implementación (mapeado a fases F0–F5)

### F0 — Prep (sin migración; solo seed + skeleton)
- [ ] Agregar los 13 permisos `SCHEDULING` a `app/core/seed.py:SEED_PERMISSIONS` (consolidar en [`_seed-and-roles.md`](../_seed-and-roles.md)).
- [ ] Subsets de rol ADMIN/ASESOR/DOCTOR vía `_seed_role` (filtro por código).
- [ ] Skeleton `backend/app/modules/scheduling/{enums,models,schemas,repositories,services,routers}/` (`enums.py` con `AppointmentSource`). Skeleton **inerte** (no registrado aún si la fase lo difiere).
- [ ] (Frontend F0) nav grupo "Agenda/Citas" (`MENU-SCHEDULING`) + iconMap; `endpoints.ts` (bloque SCHEDULING); `types/scheduling.types.ts`; skeleton inerte — ver [`frontend.md`](frontend.md).
- [ ] Smoke: login admin → el JWT contiene los 13 permisos SCHEDULING.

### F1 — AppointmentStatus + matriz (migración `0020_scheduling_status`)
- [ ] `models/appointment_status.py` + `appointment_status_transition.py` + migración `0020_scheduling_status` (`down_revision="0019_bots_engine_state"`).
- [ ] `schemas/appointment_status.py` (slug `code`, `StatusTransitionUpdate`).
- [ ] `repositories/appointment_status.py` (`get_by_code`/`get_initial`/`count_initial`/`count_using_status`/`get_by_ids`) + `appointment_status_transition.py` (`is_allowed`/`list_outgoing`/`replace_outgoing`).
- [ ] `services/appointment_status.py`: CRUD + `MULTIPLE_INITIAL_STATUS` + delete guard `APPOINTMENT_STATUS_IN_USE` + matriz (`GET`/`PUT /{id}/transitions`).
- [ ] `_seed_appointment_statuses` (8) + `_seed_appointment_transition_matrix` (base) — idempotentes por `code`.
- [ ] `routers/appointment_status.py` (CRUD + `/active` + `/{id}/transitions`). Registrar el módulo (`app/modules/__init__.py` + `main.py`).
- [ ] (Frontend F1) `/scheduling/estados` con editor de matriz — ver [`ui.md`](ui.md).
- [ ] Test seed: 8 estados; exactamente 1 `is_initial`; matriz base presente. `MULTIPLE_INITIAL_STATUS` (400), `APPOINTMENT_STATUS_IN_USE` (409).

### F2 — Appointment + availability + booking (migración `0021_scheduling_appointment`)
- [ ] `models/appointment.py` (índices + self-FK) + `appointment_status_history.py` + `appointment_change_log.py` + migración `0021_scheduling_appointment` (`down_revision="0020_scheduling_status"`).
- [ ] `schemas/appointment.py` + `availability.py` + `audit.py`.
- [ ] `repositories/appointment.py` (`list_overlapping_*` con FOR UPDATE, `list_in_range`, batch maps) + history/changelog repos.
- [ ] `services/availability.py` (`compute_available_slots` ADR-006/007 con TZ branch + N contiguos; `check_slot`) + `services/appointment.py` (9 invariantes + create FOR UPDATE→SLOT_TAKEN + get/list/update + scoping anti-IDOR).
- [ ] `routers/availability.py` (`/compute`, `/check-slot`) + `routers/appointment.py` (CRUD + `/calendar` antes de `/{id}`) + `routers/me.py`.
- [ ] (Frontend F2) tabla de citas + wizard de reserva (llama `/availability/compute`) — ver [`ui.md`](ui.md).
- [ ] Test invariantes 1-8 (cada code) + `SLOT_TAKEN` con 2 creates concurrentes/secuenciales sobre el mismo slot. Test `check-slot` available/reason. Test TZ: branch en `America/Lima` → slot local 08:00 → `13:00:00+00:00`.

### F3 — Lifecycle + audit (sin migración)
- [ ] `services/transition.py` (`transition` matriz + shortcuts confirm/check-in/start/attend/no-show/cancel/reschedule) + `attend→promote` + `APPOINTMENT_ATTENDED`.
- [ ] `cross-módulo`: `crm.enums.ActivityType += APPOINTMENT_ATTENDED`.
- [ ] Shortcuts en `routers/appointment.py` (cada uno con su permiso; `cancel` recibe `actor: CurrentAuth` para el override).
- [ ] history/changelog en `AppointmentDetail`; timeline entrelazado.
- [ ] (Frontend F3) detalle + control de estado (gated por matriz) + timeline — ver [`ui.md`](ui.md).
- [ ] Test transición válida (history) / inválida (`APPOINTMENT_TRANSITION_NOT_ALLOWED`); `cancel` con `min_hours_to_cancel` → `CANCEL_TOO_LATE` salvo override; `reschedule` (vieja RESCHEDULED + nueva con `previous_appointment_id` + revalida invariantes + `exclude_id`); `attend` → promote (lead is_won cierra, customer is_initial creado) + `APPOINTMENT_ATTENDED`; doble attend de un cliente ya cliente → no-op CRM + activity.

### F4 — Calendar grid (sin migración)
- [ ] `services/appointment.py:calendar` + `/appointments/calendar` + `/me/calendar`.
- [ ] (Frontend F4) grilla semanal (citas = bloques por color, slots libres = overlay → wizard prefilled; TZ del branch) + Mi agenda del doctor — ver [`ui.md`](ui.md).
- [ ] Test calendar: rango devuelve citas + free_slots; `/me/calendar` scoped al doctor.

### F5 — Bot facade + tools (sin migración)
- [ ] `services/bot_facade.py` (`book_from_bot`/`cancel_from_bot` SYSTEM, respetan invariantes incl. min_hours_to_cancel, emiten `LeadActivity`).
- [ ] `routers/bot_facade.py` (`/from-bot`, `/{id}/cancel-from-bot`, sin RBAC).
- [ ] `bots/services/engine/tools/scheduling.py` (3 tools `@register_tool`) + importarlo para que se registren.
- [ ] Test from-bot: respeta invariantes + emite `APPOINTMENT_BOOKED`; cancel-from-bot respeta `min_hours_to_cancel` (`CANCEL_TOO_LATE`, sin override) + emite `APPOINTMENT_CANCELLED`; las 3 tools pasan de `is_registered=false` a operativas.

Molde global = **crm** (catálogo+matriz+history+transición+promote) + **clinic/staff** (las fuentes de disponibilidad + `/me`). Lecciones operativas transversales [[feedback-medisage-operational-lessons]]: TZ client-only en el front (cualquier `new Date()`/now que afecte el render); el smoke (create_all + JSON directo) NO caza drift TS↔Pydantic ni bugs de render — la review adversaria sí; verificar que el verificador CORRIÓ (RESULT=PASS + conteo); 1 comando por tool-call (canal de tooling); gate de prod = AskUserQuestion separado del merge.
