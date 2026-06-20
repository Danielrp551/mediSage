# Módulo `crm` — Backend deep-dive

> **Última actualización**: 2026-05-31
> **Audiencia**: developer implementando `backend/app/modules/crm/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`ADR-003`](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md) (Person raíz + estados lead/customer en tablas hijas — base estructural), [`_seed-and-roles.md`](../_seed-and-roles.md) (los 15 permisos CRM + el user/role `SYSTEM` + roles `ASESOR`/`DOCTOR` ya canónicos), y los deep-dives molde [`../staff/backend.md`](../staff/backend.md) (creación NESTED, denormalización batch sin N+1, `/me`), [`../clinic/backend.md`](../clinic/backend.md) (catálogo con `code` UNIQUE + guard `*_IN_USE` 409) y [`../catalog/backend.md`](../catalog/backend.md) (CRUD + dropdown `/active`).

> **Contrato autoritativo**: este doc respeta la spec compartida de `crm` (entidades, campos, endpoints, permisos, códigos de error). Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc. El overview viejo de `crm` (que usaba `PATCH`/`/options`) queda **deprecado** y se consolida en [`README.md`](README.md) (el archivo `docs/modules/crm.md` ya fue borrado).

> **Convenciones heredadas de `catalog`/`clinic`/`staff` shipped** (repetidas aquí para que este doc se lea solo):
>
> 1. **`PUT` para updates completos** (no `PATCH`). El overview viejo de `crm` usaba `PATCH` en varios sitios — **deprecado**, reemplazado por `PUT` en TODA la ficha.
> 2. **`/active` para dropdowns** (no `/options`). Devuelve **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`), igual que `catalog`/`clinic`/`staff`. `/search` se conserva (es un endpoint funcional distinto del dropdown, lo usará el bot).
> 3. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `AlreadyExistsException`, `BadRequestException`, `ConflictException`, `ForbiddenException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; reload-via-`get_full` tras create/update (relaciones `lazy="raise"`); `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` como whitelist estricta (los campos denormalizados NO son server-sortable/filterable — búsqueda por ellos = client-side; **lección hotfix `cd10c78` de `staff`**).
> 4. **Mensajes `detail` de dominio en español, `code` en inglés**; mensajes de validators Pydantic en inglés (el front re-valida con Zod). UI 100% español.
> 5. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), lista cruda en `/active`, error `{success:false, detail, code?, errors?}`.
> 6. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `crm` arranca en `0011` (última aplicada = `0010_staff_doctor_availability`).
> 7. Patrón **audit users**: `created_by`/`updated_by` explícitos; `*_user: UserAuditInfo | None` hidratado vía `user_repository.get_audit_info_map` batch (sin N+1).

`crm` es el **módulo más grande** de medisage (12 entidades, 4 migraciones). Modela el contacto (`Person`) con dos hilos de vida coexistentes (lead y customer) en tablas hijas separadas — ver [ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md). Decisiones nuevas que este doc materializa y que se consolidarán como ADR tras las fichas: **ADR-008** (matriz de transiciones configurable) y **ADR-009** (FKs forward diferidas a módulos futuros).

## Estructura de archivos a crear

```
backend/app/modules/crm/
├── __init__.py
├── enums.py                          # ChannelType, ActivityType, ActivityOutcome
├── models/
│   ├── __init__.py                   # importa todos los modelos (registro en Base.metadata)
│   ├── person.py
│   ├── person_contact_identifier.py
│   ├── lead_status.py
│   ├── customer_status.py
│   ├── lead_status_transition.py
│   ├── customer_status_transition.py
│   ├── person_lead_status.py
│   ├── person_customer_status.py
│   ├── lead_status_history.py
│   ├── customer_status_history.py
│   ├── lead_assignment.py
│   └── lead_activity.py
├── schemas/
│   ├── __init__.py
│   ├── person.py                     # Person* + PersonContactIdentifier nested
│   ├── contact_identifier.py
│   ├── lead_status.py                # LeadStatus* + LeadStatusTransition* + StatusTransitionUpdate
│   ├── customer_status.py
│   ├── lead_lifecycle.py             # PersonLeadStatus*, transition/create requests, History*
│   ├── customer_lifecycle.py
│   ├── assignment.py                 # LeadAssignment*, AssignmentRequest
│   └── activity.py                   # LeadActivity*, ActivityCreate/Update, ActivityListRequest
├── repositories/
│   ├── __init__.py
│   ├── person.py                     # get_by_identifier, get_full, search, *_map batch
│   ├── contact_identifier.py
│   ├── lead_status.py                # get_initial, get_by_code, transition matrix helpers
│   ├── customer_status.py
│   ├── lead_status_transition.py
│   ├── customer_status_transition.py
│   ├── person_lead_status.py
│   ├── person_customer_status.py
│   ├── lead_status_history.py
│   ├── customer_status_history.py
│   ├── lead_assignment.py            # pick_round_robin_advisor (SELECT … FOR UPDATE)
│   └── lead_activity.py              # list_for_person con filtros
├── services/
│   ├── __init__.py
│   ├── person.py                     # CRUD + find_by_identifier_or_create (orquestación)
│   ├── contact_identifier.py         # dedup, is_primary
│   ├── lead_status.py                # catálogo + matriz (validaciones 1 is_initial, won⟹final)
│   ├── customer_status.py
│   ├── person_lead_status.py         # create, transition (matriz + cierre is_final)
│   ├── person_customer_status.py     # promote_from_lead
│   ├── lead_assignment.py            # reassign + assign_round_robin (concurrency-safe)
│   └── lead_activity.py              # log() helper + CRUD timeline
└── routers/
    ├── __init__.py                   # aggregator: prefix="/crm"
    ├── person.py                     # /persons/*
    ├── contact_identifier.py         # /persons/{id}/identifiers/* (anidado)
    ├── lead_status.py                # /lead-statuses/* (+ matriz)
    ├── customer_status.py            # /customer-statuses/* (+ matriz)
    ├── lead_lifecycle.py             # /persons/{id}/lead-status[/transition|/history], /promote-to-customer
    ├── customer_lifecycle.py         # /persons/{id}/customer-status[/transition|/history]
    ├── assignment.py                 # /persons/{id}/assignment[/auto] + /me/leads/list
    └── activity.py                   # /persons/{id}/activities/*
```

**No hay `models/associations.py`**: a diferencia de `staff`/`clinic`, `crm` **no introduce M:N nuevas**. Las dos tablas de transición (`lead_status_transition`, `customer_status_transition`) parecen asociaciones pero son **entidades** (tienen PK propia, mixins, `active`, son CRUD-eables vía la matriz). Por eso van como modelos normales, no como `Table()` puras.

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean):

```python
from app.modules import admin, catalog, clinic, crm, staff  # noqa: F401
```

Y registrar el aggregator en `app/main.py` (un solo `include_router`, como `clinic`/`staff`):

```python
from app.modules.crm.routers import router as crm_router

app.include_router(crm_router)  # prefix="/api/v1" + "/crm" interno
```

El aggregator `routers/__init__.py` replica el patrón de `staff/routers/__init__.py`:

```python
"""
Aggregates the crm sub-routers under one prefix. `main.py` includes this
`router` once. Order matters only inside each sub-router (/active before /{id});
the aggregator order is informational.
"""

from fastapi import APIRouter

from app.modules.crm.routers.activity import router as activity_router
from app.modules.crm.routers.assignment import router as assignment_router
from app.modules.crm.routers.contact_identifier import router as identifier_router
from app.modules.crm.routers.customer_status import router as customer_status_router
from app.modules.crm.routers.customer_lifecycle import router as customer_lifecycle_router
from app.modules.crm.routers.lead_lifecycle import router as lead_lifecycle_router
from app.modules.crm.routers.lead_status import router as lead_status_router
from app.modules.crm.routers.person import router as person_router

router = APIRouter(prefix="/crm")
router.include_router(person_router)              # /persons/*
router.include_router(identifier_router)          # /persons/{id}/identifiers/* (nested)
router.include_router(lead_status_router)         # /lead-statuses/* (+ matriz)
router.include_router(customer_status_router)     # /customer-statuses/* (+ matriz)
router.include_router(lead_lifecycle_router)      # /persons/{id}/lead-status[/transition|/history]
router.include_router(customer_lifecycle_router)  # /persons/{id}/customer-status[...]
router.include_router(assignment_router)          # /persons/{id}/assignment[/auto] + /me/leads/list
router.include_router(activity_router)            # /persons/{id}/activities/*

__all__ = ["router"]
```

## Enums — `enums.py` (en código, NO en BD)

Los tres enums son contratos estables del código (no catálogos en BD). Las columnas que los referencian son `varchar(40)` planas; Pydantic valida contra el enum, la BD almacena el slug.

```python
"""
CRM enums. NONE of these are DB catalogs — they are code-level value sets.
- ChannelType: closed set of contact channels. The slug crosses with
  conversations.ChannelAccount.channel_type (NOT a FK; a stable string contract).
- ActivityType: declared COMPLETE from day one (stable contract for the timeline)
  even though some values are emitted only when conversations/scheduling ship
  (see README §"Enum ActivityType por etapas"). Persisted as varchar(40).
- ActivityOutcome: optional qualifier for CALL_ATTEMPT activities.
"""

from __future__ import annotations

from enum import Enum


class ChannelType(str, Enum):
    whatsapp = "whatsapp"
    telegram = "telegram"
    web = "web"
    phone = "phone"
    email = "email"
    instagram = "instagram"
    facebook = "facebook"
    other = "other"


class ActivityType(str, Enum):
    # Emitted by the advisor (crm MVP).
    NOTE = "NOTE"
    CALL_ATTEMPT = "CALL_ATTEMPT"
    FOLLOW_UP_SCHEDULED = "FOLLOW_UP_SCHEDULED"
    FOLLOW_UP_COMPLETED = "FOLLOW_UP_COMPLETED"
    # Emitted by crm itself (system).
    STATUS_CHANGE = "STATUS_CHANGE"
    REASSIGNED = "REASSIGNED"
    CAMPAIGN_ATTRIBUTION = "CAMPAIGN_ATTRIBUTION"
    # Present in the enum NOW, emitted later by conversations/scheduling.
    MESSAGE_SENT = "MESSAGE_SENT"
    CONVERSATION_TAKEN = "CONVERSATION_TAKEN"
    CONVERSATION_RELEASED = "CONVERSATION_RELEASED"
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    APPOINTMENT_ATTENDED = "APPOINTMENT_ATTENDED"


class ActivityOutcome(str, Enum):
    successful = "successful"
    no_answer = "no_answer"
    busy = "busy"
    wrong_number = "wrong_number"
    not_interested = "not_interested"
    interested = "interested"
```

> **`ActivityType` se declara completo desde el inicio** aunque `crm` MVP solo emite `NOTE`/`CALL_ATTEMPT`/`FOLLOW_UP_*`/`STATUS_CHANGE`/`REASSIGNED`/`CAMPAIGN_ATTRIBUTION`. Los valores cross-módulo (`MESSAGE_SENT`, `CONVERSATION_*`, `APPOINTMENT_*`) ya están en el contrato para que el timeline no cambie de shape cuando `conversations`/`scheduling` empiecen a emitirlos. La validación de "qué tipos puede crear un asesor por la API pública" vive en el service de `lead_activity` (ver §Lógica).

## Models — SQLAlchemy 2.0

**Mixins** (de `app.shared.base_model`): `PrimaryKeyMixin` (`id`), `ActiveMixin` (`active`), `SoftDeleteMixin` (`deleted_at`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **Historiales y `LeadActivity` NO llevan `SoftDeleteMixin`** — son audit trail honesto; "borrar" una actividad es `active=false`, el historial es inmutable.

> ⚠ **Las 3 columnas forward (`source_campaign_id`, `related_appointment_id`, `related_conversation_id`) son `mapped_column(String(36), nullable=True, index=True)` SIN `ForeignKey` ni `relationship`.** Las tablas `campaign`/`appointment`/`conversation` aún NO existen; declarar el FK rompería el mapper al importar. El módulo dueño (marketing/scheduling/conversations) agrega la `FK CONSTRAINT` + `relationship` de forma aditiva (`ALTER TABLE ADD CONSTRAINT`). Patrón documentado en **ADR-009**.

### `models/person.py` — tabla `person` — PK·A·SD·T

```python
"""
Person = the root identity of a CRM contact (ADR-003). Holds ONLY identity and
basic profile data; the commercial threads (lead / customer), the owner, the
identifiers and the activity timeline live in CHILD tables. No phone/email
column here — those live in PersonContactIdentifier (multichannel, dedup-able).
No medical data (MVP).

A Person may have a PersonLeadStatus AND a PersonCustomerStatus at the same time
(active customer who becomes a lead of another campaign — ADR-003), only one of
them, or none.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.crm.models.lead_assignment import LeadAssignment
    from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
    from app.modules.crm.models.person_customer_status import PersonCustomerStatus
    from app.modules.crm.models.person_lead_status import PersonLeadStatus


class Person(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "person"

    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    second_last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)  # free text, no enum
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Children. All lazy="raise" — loaded explicitly with selectinload in the repo.
    identifiers: Mapped[list[PersonContactIdentifier]] = relationship(
        back_populates="person", lazy="raise"
    )
    # 1:0..1 — UNIQUE person_id in each child guarantees at most one active row.
    lead_status: Mapped[PersonLeadStatus | None] = relationship(
        back_populates="person", lazy="raise", uselist=False
    )
    customer_status: Mapped[PersonCustomerStatus | None] = relationship(
        back_populates="person", lazy="raise", uselist=False
    )
    assignment: Mapped[LeadAssignment | None] = relationship(
        back_populates="person", lazy="raise", uselist=False
    )
```

> **`uselist=False` + UNIQUE `person_id`**: el `PersonLeadStatus`/`PersonCustomerStatus`/`LeadAssignment` tienen UNIQUE en `person_id` (al máximo uno **vivo**, dado que `BaseRepository` filtra `deleted_at IS NULL` y los cierres soft-deletean). El `relationship` carga el actual; el historial vive en `lead_status_history`/`customer_status_history`.

### `models/person_contact_identifier.py` — tabla `person_contact_identifier` — PK·A·SD·T

```python
"""
A contact handle for a Person on a given channel (phone E.164, email, chat_id…).
The dedup rule (ADR-003) is a PARTIAL unique index on (channel_type, identifier)
WHERE deleted_at IS NULL — so the same handle can be re-assigned after a
soft-delete. `channel_type` is the ChannelType enum value (a stable slug that
crosses with conversations.ChannelAccount.channel_type — NOT a FK to a catalog).
`is_primary` marks the principal handle per (person_id, channel_type); enforced
in the service (marking a new primary unmarks the previous one).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.crm.models.person import Person


class PersonContactIdentifier(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "person_contact_identifier"
    __table_args__ = (
        # Partial UNIQUE: a live (channel_type, identifier) is globally unique
        # (single-tenant). After soft-delete the pair frees up for reassignment.
        Index(
            "uq_contact_identifier_channel_value",
            "channel_type",
            "identifier",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)  # ChannelType
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    person: Mapped[Person] = relationship(back_populates="identifiers", lazy="raise")
```

> El `postgresql_where` se expresa como string SQL (`"deleted_at IS NULL"`); en la migración se escribe el mismo índice parcial (`CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`). El alta que choca con un identifier vivo lanza `409 IDENTIFIER_TAKEN` desde el service (chequeo proactivo) **y** la BD lo respalda.

### `models/lead_status.py` — tabla `lead_status` (catálogo) — PK·A·SD·T

```python
"""
Configurable lead-stage catalog (ADR-003). `code` is a stable uppercase slug
(e.g. NUEVO). Flags drive the lifecycle without hardcoding codes:
- is_initial: EXACTLY ONE true per catalog (a new lead is born here). Service-validated.
- is_final: terminal stage (the PersonLeadStatus row is soft-deleted on entry).
- is_won: terminal-positive; only valid when is_final=true (service-validated).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class LeadStatus(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "lead_status"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # hex for badges
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_won: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

### `models/customer_status.py` — tabla `customer_status` (catálogo) — PK·A·SD·T

Idéntico a `LeadStatus` **menos `is_won`** (`is_initial` = estado por defecto al convertir; `is_final` = cliente perdido).

```python
class CustomerStatus(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "customer_status"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

### `models/lead_status_transition.py` — tabla `lead_status_transition` (matriz) — PK·A·T (SIN SD)

```python
"""
ADR-008: a configurable edge of the lead-status graph (from → to). The service
enforces transitions against THIS table. Editable by admin (LEAD_STATUSES_WRITE):
the seed installs a base matrix that the clinic later refines. No SoftDeleteMixin
— it's config: disabling an edge = active=false (keep the row) or DELETE (drop it).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class LeadStatusTransition(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "lead_status_transition"
    __table_args__ = (
        UniqueConstraint(
            "from_lead_status_id",
            "to_lead_status_id",
            name="uq_lead_status_transition_from_to",
        ),
    )

    from_lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False, index=True
    )
    to_lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False
    )
```

### `models/customer_status_transition.py` — tabla `customer_status_transition` — PK·A·T (SIN SD)

Análogo: `from_customer_status_id`, `to_customer_status_id`, UNIQUE `(from, to)`, FKs a `customer_status.id`. Seed permisivo (ver §Matriz base).

### `models/person_lead_status.py` — tabla `person_lead_status` — PK·A·SD·T

```python
"""
The CURRENT active lead-thread of a Person (ADR-003). UNIQUE person_id ⇒ at most
one LIVE row. On a transition into an is_final status the row is SOFT-DELETED
(the trace lives in lead_status_history; "reopen" = a brand-new row). So: the
existence of a non-deleted row ⟺ "this Person has an active lead".

source_campaign_id is a forward FK (ADR-009): varchar(36) + index, NO FK
constraint, NO relationship — marketing's migration adds the constraint later.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.crm.models.person import Person


class PersonLeadStatus(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "person_lead_status"
    __table_args__ = (
        UniqueConstraint("person_id", name="uq_person_lead_status_person"),
    )

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False
    )
    # Forward FK to marketing.campaign — varchar(36)+index, NO FK/relationship (ADR-009).
    source_campaign_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    entered_status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Denormalized for the persons list (last activity touched this lead).
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    person: Mapped[Person] = relationship(back_populates="lead_status", lazy="raise")
```

> **Sutileza del UNIQUE + cierre por soft-delete**: la `UniqueConstraint(person_id)` es total (no parcial). Cuando un lead se cierra (`is_final`) se hace soft-delete: la fila queda con `deleted_at` no nulo pero el UNIQUE total **seguiría bloqueando** un nuevo lead. **Por eso el cierre se modela con un índice UNIQUE parcial** `WHERE deleted_at IS NULL` (igual que `person_contact_identifier`), no con `UniqueConstraint`. La declaración correcta del modelo usa `Index(..., unique=True, postgresql_where="deleted_at IS NULL")` y la migración escribe `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`. Lo mismo aplica a `person_customer_status` y `lead_assignment`. (Se documenta como `Index` parcial; el bloque de arriba muestra `UniqueConstraint` por brevedad — **usar el índice parcial**.)

### `models/person_customer_status.py` — tabla `person_customer_status` — PK·A·SD·T

```python
class PersonCustomerStatus(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "person_customer_status"
    __table_args__ = (
        Index(
            "uq_person_customer_status_person",
            "person_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    customer_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_status.id"), nullable=False
    )
    became_customer_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False  # first time (kept across status changes)
    )
    entered_status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False  # current status entered
    )

    person: Mapped[Person] = relationship(back_populates="customer_status", lazy="raise")
```

> Sin `source_campaign_id` (la atribución de campaña es del hilo lead).

### `models/lead_status_history.py` — tabla `lead_status_history` — PK·A·T (SIN SD)

```python
"""
Immutable transition log of a Person's lead thread. NO SoftDeleteMixin (honest
audit trail). from_lead_status_id is NULL on the very first row (creation).
changed_by is a logical FK to user.id (NULL/SYSTEM when automatic).
source_campaign_id is a forward FK (ADR-009) — only filled at creation.
"""

class LeadStatusHistory(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "lead_status_history"

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    from_lead_status_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=True
    )
    to_lead_status_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lead_status.id"), nullable=False
    )
    # Forward FK to marketing.campaign — NO FK constraint/relationship (ADR-009).
    source_campaign_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # logical FK
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### `models/customer_status_history.py` — tabla `customer_status_history` — PK·A·T (SIN SD)

Análogo, **sin `source_campaign_id`**: `person_id`, `from_customer_status_id` (nullable), `to_customer_status_id`, `changed_at`, `changed_by` (nullable), `reason` (nullable).

### `models/lead_assignment.py` — tabla `lead_assignment` — PK·A·SD·T

```python
"""
The advisor who OWNS the active lead of a Person. UNIQUE person_id (partial,
WHERE deleted_at IS NULL — at most one live owner). Reassignment = soft-delete
the current row + insert a new one + LeadActivity(REASSIGNED), in ONE tx.
advisor_user_id / assigned_by are logical FKs to user.id (assigned_by NULL when
round-robin auto).
"""

class LeadAssignment(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "lead_assignment"
    __table_args__ = (
        Index(
            "uq_lead_assignment_person",
            "person_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    advisor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=False, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # NULL=auto
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    person: Mapped[Person] = relationship(back_populates="assignment", lazy="raise")
```

> `advisor_user_id` SÍ tiene `ForeignKey("user.id")` (el módulo `admin.user` ya existe). `assigned_by` es FK lógica (string, sin constraint) porque puede ser el `SYSTEM` user o NULL en round-robin auto.

### `models/lead_activity.py` — tabla `lead_activity` (polimórfica) — PK·A·T (SIN SD)

```python
"""
Polymorphic timeline of a Person (ADR-003): notes, call attempts, follow-ups,
and system events (status changes, reassignments, campaign attribution; later
conversations/scheduling events). NO SoftDeleteMixin — "delete" = active=false
(the normal timeline filters active=true). `activity_type` is the ActivityType
enum value. `payload` JSONB carries type-specific data. related_appointment_id /
related_conversation_id are forward FKs (ADR-009): varchar(36)+index, NO FK
constraint, NO relationship (scheduling/conversations add them later).
"""

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB

class LeadActivity(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "lead_activity"

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    advisor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True  # NULL/SYSTEM for system events
    )
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False)  # ActivityType
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ActivityOutcome
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Forward FKs (ADR-009) — NO FK constraint/relationship.
    related_appointment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    related_conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
```

### `models/__init__.py`

```python
"""
Importing models here registers them on Base.metadata before Alembic reads the
schema and before string-based relationship() resolution runs. Order: parents
(catalogs, person) before children.
"""

from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.lead_status_transition import LeadStatusTransition
from app.modules.crm.models.customer_status_transition import CustomerStatusTransition
from app.modules.crm.models.person_lead_status import PersonLeadStatus
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.crm.models.lead_status_history import LeadStatusHistory
from app.modules.crm.models.customer_status_history import CustomerStatusHistory
from app.modules.crm.models.lead_assignment import LeadAssignment
from app.modules.crm.models.lead_activity import LeadActivity

__all__ = [
    "Person", "PersonContactIdentifier",
    "LeadStatus", "CustomerStatus",
    "LeadStatusTransition", "CustomerStatusTransition",
    "PersonLeadStatus", "PersonCustomerStatus",
    "LeadStatusHistory", "CustomerStatusHistory",
    "LeadAssignment", "LeadActivity",
]
```

**Lazy strategy**: como en `clinic`/`catalog`/`staff`, todas las relaciones en `lazy="raise"`. Se cargan con `selectinload(...)` explícito en el repo, nunca implícitamente. Las transition tables y los historiales NO tienen relación ORM hacia `Person` (se consultan por `from_*`/`person_id` directamente).

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (idénticas a [`../staff/backend.md`](../staff/backend.md#schemas-pydantic-v2--completos)):
>
> 1. **No usar Ellipsis (`...`)** en `Field(...)`. Campo sin `default=` ya es obligatorio.
> 2. **`Annotated`** solo para parámetros HTTP (`Query`, `Path`) en routers.
> 3. **Validators**: `@field_validator` single-field, `@model_validator(mode="after")` cross-field.
> 4. **Mensajes de validator en inglés** (van al detalle 422). El texto user-facing en español vive en el Zod del frontend.

### `schemas/person.py` (Person + PersonContactIdentifier nested)

```python
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType


class PersonContactIdentifierInput(BaseModel):
    """Initial identifier supplied INLINE in PersonCreate (optional list). The
    standalone CRUD lives in contact_identifier.py."""

    channel_type: ChannelType
    identifier: str = Field(min_length=1, max_length=255)
    is_primary: bool = False
    verified: bool = False


class PersonCreate(BaseModel):
    """Creates a Person and (optionally) its initial identifiers in one tx. Does
    NOT create a lead automatically (that's POST /lead-status or
    find_by_identifier_or_create)."""

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    birth_date: date_type | None = None
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    identifiers: list[PersonContactIdentifierInput] = Field(default_factory=list)

    @field_validator("identifiers")
    @classmethod
    def _no_dup_identifiers(
        cls, v: list[PersonContactIdentifierInput]
    ) -> list[PersonContactIdentifierInput]:
        seen = {(i.channel_type, i.identifier) for i in v}
        if len(seen) != len(v):
            raise ValueError("identifiers must not contain duplicate (channel_type, identifier)")
        # At most one primary per channel_type in the incoming set.
        primaries: dict[ChannelType, int] = {}
        for i in v:
            if i.is_primary:
                primaries[i.channel_type] = primaries.get(i.channel_type, 0) + 1
        if any(c > 1 for c in primaries.values()):
            raise ValueError("at most one primary identifier per channel_type")
        return v


class PersonUpdate(BaseModel):
    """Partial update of identity fields. Identifiers/lead/customer/assignment are
    managed via their own endpoints, not here."""

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    birth_date: date_type | None = None
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    active: bool | None = None


class PrimaryIdentifierInfo(BaseModel):
    """Compact shape for the denormalized primary identifier in the list row."""

    model_config = ConfigDict(from_attributes=True)
    channel_type: ChannelType
    identifier: str
    verified: bool


class StatusBadge(BaseModel):
    """Compact lead/customer status for badges (code/name/color)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None


class PersonItem(BaseModel):
    """Row of the persons table. Denormalizes the primary identifier, the current
    lead/customer status badges, the assigned advisor and last_activity_at so the
    list never needs the front to join. These are NOT columns of `person` → they
    are NOT in ALLOWED_FIELDS (lesson cd10c78): client-side search by name/handle,
    deep-link filters by *_id translated to EXISTS in the repo."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str  # f"{first_name} {last_name} {second_last_name or ''}".strip()
    first_name: str
    last_name: str
    second_last_name: str | None
    document_type: str | None
    document_number: str | None
    active: bool
    primary_identifier: PrimaryIdentifierInfo | None = None
    lead_status: StatusBadge | None = None
    customer_status: StatusBadge | None = None
    assigned_advisor: UserAuditInfo | None = None
    last_activity_at: datetime | None = None
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class PersonDetail(PersonItem):
    """Full profile for the detail page. Adds the free-text/profile fields and the
    resolved identifiers collection (soft-deleted filtered out)."""

    birth_date: date_type | None
    gender: str | None
    address: str | None
    notes: str | None
    identifiers: list[ContactIdentifierItem]  # from contact_identifier.py


class PersonOption(BaseModel):
    """Dropdown shape — GET /persons/active. Used by future modules (scheduling)
    and by /persons/search (the bot path)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    document_number: str | None = None
    primary_identifier: PrimaryIdentifierInfo | None = None
```

> **`full_name` denormalizado**: `Person` no tiene una columna `full_name`; el service lo arma (`f"{first_name} {last_name} {second_last_name or ''}".strip()`). Por eso `_to_item`/`_to_detail` lo pasan como kwarg explícito (mismo patrón que `staff.DoctorItem.full_name`).

### `schemas/contact_identifier.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType


class ContactIdentifierCreate(BaseModel):
    channel_type: ChannelType
    identifier: str = Field(min_length=1, max_length=255)
    is_primary: bool = False
    verified: bool = False


class ContactIdentifierUpdate(BaseModel):
    """Only the mutable fields. channel_type/identifier ARE editable (correcting a
    typo) but re-trigger the dedup guard. is_primary toggling unmarks the previous
    primary of the same channel."""

    channel_type: ChannelType | None = None
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    is_primary: bool | None = None
    verified: bool | None = None
    active: bool | None = None


class ContactIdentifierItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    channel_type: ChannelType
    identifier: str
    is_primary: bool
    verified: bool
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
```

### `schemas/lead_status.py` (catálogo + matriz + request de transiciones)

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class LeadStatusCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool = False
    is_final: bool = False
    is_won: bool = False
    display_order: int = 0

    @model_validator(mode="after")
    def _won_requires_final(self) -> LeadStatusCreate:
        if self.is_won and not self.is_final:
            raise ValueError("is_won requires is_final")
        return self


class LeadStatusUpdate(BaseModel):
    """`code` is immutable (stable slug) → not declared. is_won⟹is_final
    re-validated when both present after merge (the service merges)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool | None = None
    is_final: bool | None = None
    is_won: bool | None = None
    display_order: int | None = None
    active: bool | None = None


class LeadStatusItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    is_initial: bool
    is_final: bool
    is_won: bool
    display_order: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class LeadStatusOption(BaseModel):
    """Dropdown / badge shape — GET /lead-statuses/active (raw list)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_initial: bool = False
    is_final: bool = False
    is_won: bool = False


class StatusTransitionUpdate(BaseModel):
    """Body of PUT /lead-statuses/{id}/transitions — REPLACES the outgoing edges
    of one status with exactly these targets."""

    to_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_dupes(self) -> StatusTransitionUpdate:
        if len(self.to_ids) != len(set(self.to_ids)):
            raise ValueError("to_ids must not contain duplicates")
        return self
```

> `schemas/customer_status.py` es idéntico **menos `is_won`** y sin `_won_requires_final`; reusa `StatusTransitionUpdate`.

### `schemas/lead_lifecycle.py` (PersonLeadStatus + requests + History)

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.schemas.lead_status import LeadStatusOption


class LeadStatusCreateRequest(BaseModel):
    """Body of POST /persons/{id}/lead-status — the lead is born in the is_initial
    status; only the source/reason are supplied. source_campaign_id forward (ADR-009)."""

    source_campaign_id: str | None = Field(default=None, max_length=36)
    reason: str | None = Field(default=None, max_length=255)


class LeadStatusTransitionRequest(BaseModel):
    """Body of POST /persons/{id}/lead-status/transition."""

    to_lead_status_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class PersonLeadStatusDetail(BaseModel):
    """Current lead thread of a Person (or the service returns null when none)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    lead_status: LeadStatusOption  # denormalized current LeadStatus (clave `lead_status`, NO `status`)
    source_campaign_id: str | None
    entered_status_at: datetime
    last_activity_at: datetime | None
    created_on: datetime
    # Sin `active`/`updated_on` — el detalle del estado activo es liviano (espeja types/crm.types.ts).


class LeadStatusHistoryItem(BaseModel):
    """One row of the lead status timeline. from_lead_status null on creation."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    # Claves `from_lead_status`/`to_lead_status` (NO `from_status`/`to_status`) — el badge
    # consume id/code/name/color/is_final/is_won (espeja LeadStatusSummary de types/crm.types.ts).
    from_lead_status: LeadStatusOption | None = None  # denormalized
    to_lead_status: LeadStatusOption                  # denormalized
    source_campaign_id: str | None
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None
```

> `schemas/customer_lifecycle.py` análogo: `CustomerStatusTransitionRequest {to_customer_status_id, reason?}`, `PromoteToCustomerRequest {reason?}`, `PersonCustomerStatusDetail` (campo **`customer_status`** — NO `status`; `became_customer_at` + `entered_status_at` + `created_on`, sin `active`/`updated_on`), `CustomerStatusHistoryItem` (**`from_customer_status`/`to_customer_status`**). Espeja `types/crm.types.ts` (contrato front).

### `schemas/assignment.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo


class AssignmentRequest(BaseModel):
    """Body of PUT /persons/{id}/assignment — manual assign / "asignarme"."""

    advisor_user_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=255)


class LeadAssignmentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    advisor: UserAuditInfo            # denormalized from user
    assigned_at: datetime
    assigned_by: str | None
    assigned_by_user: UserAuditInfo | None = None
    reason: str | None
```

> `POST /persons/{id}/assignment/auto` no lleva body (round-robin). **`/me/leads/list` devuelve `PaginatedResponse[MyLeadItem]` (NO `PersonItem`)**: `MyLeadItem = {person_id, full_name, primary_identifier, lead_status, last_activity_at, next_follow_up_at}` — `next_follow_up_at` (el `FOLLOW_UP_SCHEDULED` pendiente más próximo) se denormaliza para la bandeja del asesor. Espeja `types/crm.types.ts`.

### `schemas/activity.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ActivityOutcome, ActivityType

# Types an advisor may create via the public API (the rest are system/cross-module).
ADVISOR_ACTIVITY_TYPES = {
    ActivityType.NOTE,
    ActivityType.CALL_ATTEMPT,
    ActivityType.FOLLOW_UP_SCHEDULED,
    ActivityType.FOLLOW_UP_COMPLETED,
}


class ActivityCreate(BaseModel):
    """POST /persons/{id}/activities — only advisor-emitted types allowed."""

    activity_type: ActivityType
    content: str | None = None
    scheduled_for: datetime | None = None
    completed_at: datetime | None = None
    outcome: ActivityOutcome | None = None
    payload: dict | None = None

    @model_validator(mode="after")
    def _advisor_type_only(self) -> ActivityCreate:
        if self.activity_type not in ADVISOR_ACTIVITY_TYPES:
            raise ValueError("activity_type not allowed via this endpoint")
        if self.activity_type == ActivityType.FOLLOW_UP_SCHEDULED and self.scheduled_for is None:
            raise ValueError("scheduled_for is required for FOLLOW_UP_SCHEDULED")
        return self


class ActivityUpdate(BaseModel):
    """PUT /persons/{id}/activities/{act_id} — only these fields are editable."""

    content: str | None = None
    outcome: ActivityOutcome | None = None
    completed_at: datetime | None = None
    scheduled_for: datetime | None = None


class ActivityListRequest(BaseModel):
    """Body of POST /persons/{id}/activities/list — typed filters for the timeline."""

    activity_type: list[ActivityType] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    activity_type: ActivityType
    advisor_user_id: str | None           # raw FK lógica (null/SYSTEM → actividad de sistema)
    advisor: UserAuditInfo | None = None  # denormalized; null for SYSTEM-only events
    content: str | None
    scheduled_for: datetime | None
    completed_at: datetime | None
    outcome: ActivityOutcome | None
    payload: dict | None
    related_appointment_id: str | None
    related_conversation_id: str | None
    active: bool
    # Audit cols (LeadActivity tiene TimestampMixin; NO SoftDelete) — consistentes con el
    # resto de los *Item del codebase y con types/crm.types.ts.
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
```

## Repositories

`ALLOWED_FIELDS` es el whitelist de columnas filtrable/ordenable desde el frontend (ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md)). **Lección hotfix `cd10c78` de `staff`**: solo columnas **reales** de la tabla — nunca campos denormalizados (ordenar/filtrar por ellos da 400). El filtro por estado/asesor en `persons` se hace con deep-link (`?lead_status_id=`, `?customer_status_id=`, `?advisor_user_id=`) traducido a `EXISTS`/JOIN como `staff` hace con `?branch_id=`.

### `repositories/person.py`

```python
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.crm.models.lead_assignment import LeadAssignment
from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.crm.models.person_lead_status import PersonLeadStatus
from app.shared.base_repository import BaseRepository


class PersonRepository(BaseRepository[Person]):
    # ONLY real columns of `person`. full_name/primary_identifier/lead_status/
    # customer_status/assigned_advisor/last_activity_at are DENORMALIZED → NOT here
    # (lesson cd10c78). Default sort = created_on desc.
    ALLOWED_FIELDS: set[str] = {
        "first_name", "last_name", "second_last_name",
        "document_type", "document_number", "active",
        "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Person)

    async def get_by_identifier(
        self, db: AsyncSession, channel_type: str, identifier: str
    ) -> Person | None:
        """Resolve the Person owning a live (channel_type, identifier). Powers
        /persons/search and find_by_identifier_or_create (the bot path)."""
        result = await db.execute(
            select(Person)
            .join(PersonContactIdentifier, PersonContactIdentifier.person_id == Person.id)
            .where(
                PersonContactIdentifier.channel_type == channel_type,
                PersonContactIdentifier.identifier == identifier,
                PersonContactIdentifier.deleted_at.is_(None),
                Person.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, person_id: str) -> Person | None:
        """Eager-load identifiers (live), the current lead_status, customer_status
        and assignment (each 1:0..1). with_loader_criteria filters soft-deleted
        children at load time."""
        return await self.get_by_id(
            db,
            person_id,
            load=(
                selectinload(Person.identifiers),
                selectinload(Person.lead_status),
                selectinload(Person.customer_status),
                selectinload(Person.assignment),
                with_loader_criteria(
                    PersonContactIdentifier,
                    PersonContactIdentifier.deleted_at.is_(None),
                    include_aliases=True,
                ),
                with_loader_criteria(
                    PersonLeadStatus, PersonLeadStatus.deleted_at.is_(None), include_aliases=True
                ),
                with_loader_criteria(
                    PersonCustomerStatus, PersonCustomerStatus.deleted_at.is_(None), include_aliases=True
                ),
                with_loader_criteria(
                    LeadAssignment, LeadAssignment.deleted_at.is_(None), include_aliases=True
                ),
            ),
        )

    async def search(
        self,
        db: AsyncSession,
        q: str | None = None,
        channel_type: str | None = None,
        identifier: str | None = None,
        limit: int = 20,
    ) -> list[Person]:
        """Functional search for the bot (/persons/search). Exact identifier match
        when (channel_type, identifier) given; else ILIKE on name/document."""
        if channel_type is not None and identifier is not None:
            person = await self.get_by_identifier(db, channel_type, identifier)
            return [person] if person is not None else []
        stmt = select(Person).where(Person.deleted_at.is_(None)).limit(limit)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Person.first_name.ilike(like),
                    Person.last_name.ilike(like),
                    Person.document_number.ilike(like),
                )
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self, db: AsyncSession) -> list[Person]:
        result = await db.execute(
            select(Person)
            .where(Person.active.is_(True), Person.deleted_at.is_(None))
            .order_by(Person.created_on.desc())
        )
        return list(result.scalars().all())


person_repository = PersonRepository()
```

> **Deep-link filters (`?lead_status_id=`, `?advisor_user_id=`, `?has_active_lead=`)** los aplica el **service** sobre el `QueryRequest` traduciéndolos a `EXISTS` sub-selects sobre `person_lead_status`/`lead_assignment` antes de delegar en `get_paginated` (mismo patrón que `staff.list_active(branch_id=...)`). NO se exponen como `ALLOWED_FIELDS` porque no son columnas de `person`.

### `repositories/person_lead_status.py` (denormalización batch sin N+1)

```python
class PersonLeadStatusRepository(BaseRepository[PersonLeadStatus]):
    ALLOWED_FIELDS: set[str] = set()  # never listed directly; queried by person_id

    def __init__(self) -> None:
        super().__init__(PersonLeadStatus)

    async def get_active_for_person(self, db: AsyncSession, person_id: str) -> PersonLeadStatus | None:
        result = await db.execute(
            select(PersonLeadStatus).where(
                PersonLeadStatus.person_id == person_id,
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def status_map(self, db: AsyncSession, person_ids: list[str]) -> dict[str, LeadStatus]:
        """Batch the current LeadStatus of a page of persons — one query, no N+1.
        Powers PersonItem.lead_status. Joins through the live PersonLeadStatus."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(PersonLeadStatus.person_id, LeadStatus)
            .join(LeadStatus, LeadStatus.id == PersonLeadStatus.lead_status_id)
            .where(
                PersonLeadStatus.person_id.in_(person_ids),
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def last_activity_map(self, db: AsyncSession, person_ids: list[str]) -> dict[str, datetime]:
        """Batch last_activity_at per person (denormalized) — PersonItem column."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(PersonLeadStatus.person_id, PersonLeadStatus.last_activity_at)
            .where(
                PersonLeadStatus.person_id.in_(person_ids),
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return {row[0]: row[1] for row in result.all() if row[1] is not None}

    async def count_using_status(self, db: AsyncSession, lead_status_id: str) -> int:
        """Guard for DELETE /lead-statuses/{id} (409 LEAD_STATUS_IN_USE). Counts live
        PersonLeadStatus rows referencing it (history is a separate, weaker guard)."""
        result = await db.execute(
            select(func.count())
            .select_from(PersonLeadStatus)
            .where(
                PersonLeadStatus.lead_status_id == lead_status_id,
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
```

> `customer_status_map` / `assignment_map` (advisor `User`) son análogos y batch igual. El service de `persons.list_paginated` hace 4-5 lookups batch (primary identifier, lead status, customer status, advisor user, last_activity) + el `get_audit_info_map` — todos por `IN (person_ids)`, cero N+1 (patrón idéntico a `staff`/`clinic`).

### `repositories/lead_status.py` (matriz de transiciones)

```python
class LeadStatusRepository(BaseRepository[LeadStatus]):
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "is_initial", "is_final", "is_won", "display_order",
        "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(LeadStatus)

    async def get_by_code(self, db: AsyncSession, code: str) -> LeadStatus | None:
        result = await db.execute(
            select(LeadStatus).where(LeadStatus.code == code, LeadStatus.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_initial(self, db: AsyncSession) -> LeadStatus | None:
        """The single is_initial status (NO_INITIAL_LEAD_STATUS if none)."""
        result = await db.execute(
            select(LeadStatus).where(
                LeadStatus.is_initial.is_(True), LeadStatus.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def count_initial(self, db: AsyncSession, exclude_id: str | None = None) -> int:
        """Guard: exactly one is_initial. Used on create/update to detect a 2nd one."""
        stmt = select(func.count()).select_from(LeadStatus).where(
            LeadStatus.is_initial.is_(True), LeadStatus.deleted_at.is_(None)
        )
        if exclude_id is not None:
            stmt = stmt.where(LeadStatus.id != exclude_id)
        return (await db.execute(stmt)).scalar_one()
```

```python
class LeadStatusTransitionRepository(BaseRepository[LeadStatusTransition]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(LeadStatusTransition)

    async def is_allowed(self, db: AsyncSession, from_id: str, to_id: str) -> bool:
        """Enforcement core of the transition service (ADR-008)."""
        result = await db.execute(
            select(LeadStatusTransition.id).where(
                LeadStatusTransition.from_lead_status_id == from_id,
                LeadStatusTransition.to_lead_status_id == to_id,
                LeadStatusTransition.active.is_(True),
            )
        )
        return result.scalars().first() is not None

    async def list_outgoing(self, db: AsyncSession, from_id: str) -> list[str]:
        """to_ids reachable from a status — GET /lead-statuses/{id}/transitions."""
        result = await db.execute(
            select(LeadStatusTransition.to_lead_status_id).where(
                LeadStatusTransition.from_lead_status_id == from_id,
                LeadStatusTransition.active.is_(True),
            )
        )
        return [row[0] for row in result.all()]

    async def replace_outgoing(
        self, db: AsyncSession, from_id: str, to_ids: list[str]
    ) -> None:
        """PUT /lead-statuses/{id}/transitions — delete outgoing edges + reinsert
        the new set (transition tables have no SD; DELETE is real). One tx."""
        await db.execute(
            delete(LeadStatusTransition).where(
                LeadStatusTransition.from_lead_status_id == from_id
            )
        )
        # caller inserts the new rows (needs audit columns) — see service.
```

### `repositories/lead_assignment.py` — `pick_round_robin_advisor` (SELECT … FOR UPDATE)

```python
class LeadAssignmentRepository(BaseRepository[LeadAssignment]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(LeadAssignment)

    async def get_active_for_person(self, db: AsyncSession, person_id: str) -> LeadAssignment | None:
        result = await db.execute(
            select(LeadAssignment).where(
                LeadAssignment.person_id == person_id,
                LeadAssignment.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def pick_round_robin_advisor(self, db: AsyncSession) -> str | None:
        """Pick the ASESOR with the fewest active leads (ties → oldest assignment
        first). FOR UPDATE on the candidate row blocks a concurrent auto-assign
        from picking the same advisor (ADR-003 "round-robin in the same tx").
        Returns the advisor user_id, or None when no ASESOR is available."""
        # 1) candidate users: active, not deleted, holding the ASESOR role.
        #    role/permission join lives in admin; we read user_role + role here.
        active_lead_count = (
            select(func.count(LeadAssignment.id))
            .where(
                LeadAssignment.advisor_user_id == User.id,
                LeadAssignment.deleted_at.is_(None),
            )
            .scalar_subquery()
            .label("lead_count")
        )
        last_assigned = (
            select(func.max(LeadAssignment.assigned_at))
            .where(LeadAssignment.advisor_user_id == User.id)
            .scalar_subquery()
            .label("last_assigned")
        )
        stmt = (
            select(User.id)
            .join(user_role, user_role.c.user_id == User.id)
            .join(Role, Role.id == user_role.c.role_id)
            .where(
                Role.name == "ASESOR",
                User.active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(active_lead_count.asc(), last_assigned.asc().nulls_first())
            .limit(1)
            .with_for_update()  # SELECT ... FOR UPDATE on the chosen candidate row
        )
        result = await db.execute(stmt)
        return result.scalars().first()


lead_assignment_repository = LeadAssignmentRepository()
```

> **`with_for_update()`** emite `SELECT … FOR UPDATE`: dos requests de auto-asignación concurrentes serializan en el candidato elegido; el segundo espera al commit del primero y re-evalúa los conteos, evitando que ambos asignen al mismo asesor. El UNIQUE parcial sobre `lead_assignment.person_id` es el backstop final.

### `repositories/lead_activity.py` — `list_for_person` con filtros

```python
class LeadActivityRepository(BaseRepository[LeadActivity]):
    ALLOWED_FIELDS: set[str] = set()  # listed via the typed ActivityListRequest

    def __init__(self) -> None:
        super().__init__(LeadActivity)

    async def list_for_person(
        self,
        db: AsyncSession,
        person_id: str,
        activity_types: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[LeadActivity]:
        """Timeline of a Person (active=true only), newest first. Filters by type
        list and created_on range."""
        stmt = (
            select(LeadActivity)
            .where(
                LeadActivity.person_id == person_id,
                LeadActivity.active.is_(True),
            )
            .order_by(LeadActivity.created_on.desc())
        )
        if activity_types:
            stmt = stmt.where(LeadActivity.activity_type.in_(activity_types))
        if date_from is not None:
            stmt = stmt.where(LeadActivity.created_on >= date_from)
        if date_to is not None:
            stmt = stmt.where(LeadActivity.created_on <= date_to)
        result = await db.execute(stmt)
        return list(result.scalars().all())
```

## API contracts

Envelopes del template (idénticos a [`../staff/backend.md`](../staff/backend.md#api-contracts)):
- **Single**: `{ "success": true, "data": <T> }`
- **Paginated**: `{ "success": true, "data": { "items": [...], "total": N, "skip": 0, "limit": 10 } }`
- **Lista cruda** (`/active`): el body es directamente `[...]`.
- **Error**: `{ "success": false, "detail": "...", "code"?: "...", "errors"?: [...] }`

Prefijo común: `/api/v1/crm/`. Listados paginados con `POST /<recurso>/list` + `QueryRequest`. `PUT` (no `PATCH`); `/active` antes de `/{id}` en el router.

### Person

#### `POST /api/v1/crm/persons/list` — `PERSONS_READ` → `PaginatedResponse[PersonItem]`

**Request** (`QueryRequest`):
```json
{
  "pagination": { "skip": 0, "limit": 10 },
  "sorting":    { "sort_by": "created_on", "sort_order": "desc" },
  "filters": { "filters": [ { "operator": "AND", "conditions": [
    { "field": "active", "operator": "eq", "value": true }
  ] } ] }
}
```

> Filtros por **estado lead/cliente/asesor/"con lead activo"** se pasan como **query params deep-link** (`?lead_status_id=`, `?customer_status_id=`, `?advisor_user_id=`, `?has_active_lead=true`) que el service traduce a `EXISTS`; NO van en `conditions` (no son columnas de `person`). Búsqueda por nombre/identificador = client-side sobre las filas denormalizadas.

**Response**:
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "p1a2...",
        "full_name": "Lucía Fernández Soto",
        "first_name": "Lucía", "last_name": "Fernández", "second_last_name": "Soto",
        "document_type": "DNI", "document_number": "70123456",
        "active": true,
        "primary_identifier": { "channel_type": "whatsapp", "identifier": "+51999111222", "verified": true },
        "lead_status":     { "id": "ls3...", "code": "CONTACTADO", "name": "Contactado", "color": "#3B82F6" },
        "customer_status": null,
        "assigned_advisor": { "id": "u5...", "full_name": "Ana Torres", "email": "ana@medisage.pe" },
        "last_activity_at": "2026-05-31T15:04:00+00:00",
        "created_on": "2026-05-29T14:23:10+00:00",
        "created_by": "00000000-0000-0000-0000-000000000002",
        "created_by_user": { "id": "...", "full_name": "System Internal", "email": "system@medisage.internal" },
        "updated_on": "2026-05-31T15:04:00+00:00",
        "updated_by": "u5...",
        "updated_by_user": { "id": "u5...", "full_name": "Ana Torres", "email": "ana@medisage.pe" }
      }
    ],
    "total": 1, "skip": 0, "limit": 10
  }
}
```

#### `POST /api/v1/crm/persons` — `PERSONS_CREATE` → `201 SingleResponse[PersonDetail]`

**Request** (`PersonCreate`, identifiers opcionales inline):
```json
{
  "first_name": "Lucía", "last_name": "Fernández", "second_last_name": "Soto",
  "document_type": "DNI", "document_number": "70123456",
  "gender": "femenino",
  "identifiers": [
    { "channel_type": "whatsapp", "identifier": "+51999111222", "is_primary": true, "verified": false },
    { "channel_type": "email", "identifier": "lucia@gmail.com", "is_primary": true }
  ]
}
```

**Response 201** `SingleResponse[PersonDetail]` (incluye `identifiers`). **NO** crea lead automáticamente.

**Error 409** (uno de los identifiers ya está tomado por otra persona viva):
```json
{ "success": false, "detail": "El identificador 'whatsapp:+51999111222' ya está registrado", "code": "IDENTIFIER_TAKEN" }
```

#### `GET /api/v1/crm/persons/{id}` — `PERSONS_READ` → `SingleResponse[PersonDetail]`

**Error 404**:
```json
{ "success": false, "detail": "Persona no encontrada", "code": "PERSON_NOT_FOUND" }
```

#### `PUT /api/v1/crm/persons/{id}` — `PERSONS_UPDATE` → `SingleResponse[PersonDetail]`

Subset de identidad; identifiers/lead/customer/assignment se gestionan por sus propios endpoints.

#### `DELETE /api/v1/crm/persons/{id}` — `PERSONS_DELETE` → `204` (soft-delete)

Soft-deletea la `Person`; identifiers/lead/customer/assignment/activities quedan colgados pero filtrados por el `deleted_at` de la persona en cualquier lectura.

#### `GET /api/v1/crm/persons/active` — `PERSONS_READ` → lista cruda `list[PersonOption]`
```json
[ { "id": "p1a2...", "full_name": "Lucía Fernández Soto", "document_number": "70123456", "primary_identifier": { "channel_type": "whatsapp", "identifier": "+51999111222", "verified": true } } ]
```

#### `GET /api/v1/crm/persons/search?q=&channel_type=&identifier=` — `PERSONS_READ` → `SingleResponse[list[PersonOption]]`

Si vienen `channel_type` + `identifier` → match exacto (lo usará el bot). Si viene `q` → ILIKE sobre nombre/documento. Devuelve lista (vacía si no hay match, no 404).

### PersonContactIdentifier (anidado bajo `/persons/{id}/identifiers`)

#### `GET /persons/{id}/identifiers` — `PERSONS_READ` → `SingleResponse[list[ContactIdentifierItem]]`
#### `POST /persons/{id}/identifiers` — `PERSONS_UPDATE` → `201 SingleResponse[ContactIdentifierItem]`

**Error 409** (dedup):
```json
{ "success": false, "detail": "El identificador 'phone:+51999111222' ya está registrado", "code": "IDENTIFIER_TAKEN" }
```

#### `PUT /persons/{id}/identifiers/{ident_id}` — `PERSONS_UPDATE` → `SingleResponse[ContactIdentifierItem]`

Marcar `is_primary=true` desmarca el principal anterior del mismo canal (en una tx).

**Error 404** (ownership — no existe o es de otra persona):
```json
{ "success": false, "detail": "Identificador no encontrado", "code": "IDENTIFIER_NOT_FOUND" }
```

#### `DELETE /persons/{id}/identifiers/{ident_id}` — `PERSONS_UPDATE` → `204` (soft-delete)

### Catálogo LeadStatus (+ matriz)

#### `POST /lead-statuses/list` — `LEAD_STATUSES_READ` → `PaginatedResponse[LeadStatusItem]`
#### `POST /lead-statuses` — `LEAD_STATUSES_WRITE` → `201 SingleResponse[LeadStatusItem]`

**Error 409** (`code` duplicado):
```json
{ "success": false, "detail": "Ya existe un estado de lead con el código 'NUEVO'", "code": "LEAD_STATUS_CODE_TAKEN" }
```

**Error 400** (segundo `is_initial`):
```json
{ "success": false, "detail": "Ya existe un estado inicial; solo puede haber uno", "code": "MULTIPLE_INITIAL_STATUS" }
```

**Error 400** (`is_won` sin `is_final`):
```json
{ "success": false, "detail": "Un estado ganado debe ser también final", "code": "WON_REQUIRES_FINAL" }
```

#### `PUT /lead-statuses/{id}` — `LEAD_STATUSES_WRITE` → `SingleResponse[LeadStatusItem]`

`code` inmutable (no se declara en `LeadStatusUpdate`). Re-valida `MULTIPLE_INITIAL_STATUS` y `WON_REQUIRES_FINAL` sobre el merge.

#### `DELETE /lead-statuses/{id}` — `LEAD_STATUSES_WRITE` → `204`

**Error 409** (en uso):
```json
{ "success": false, "detail": "No se puede eliminar: hay leads en este estado", "code": "LEAD_STATUS_IN_USE" }
```

**Error 404** → `LEAD_STATUS_NOT_FOUND`.

#### `GET /lead-statuses/active` — `LEAD_STATUSES_READ` → lista cruda `list[LeadStatusOption]`
```json
[
  { "id": "ls1...", "code": "NUEVO", "name": "Nuevo", "color": "#9CA3AF", "is_initial": true, "is_final": false, "is_won": false },
  { "id": "ls6...", "code": "CITA_AGENDADA", "name": "Cita agendada", "color": "#22C55E", "is_initial": false, "is_final": true, "is_won": true }
]
```

#### `GET /lead-statuses/{id}/transitions` — `LEAD_STATUSES_READ` → `SingleResponse[list[LeadStatusOption]]`

Los estados a los que **puede ir** desde `{id}` (resuelve `to_ids` a `LeadStatusOption`). Vacío si terminal.

#### `PUT /lead-statuses/{id}/transitions` — `LEAD_STATUSES_WRITE` → `SingleResponse[list[LeadStatusOption]]`

**Request** (`StatusTransitionUpdate`): reemplaza las aristas de salida.
```json
{ "to_ids": ["ls2...", "ls7..."] }
```

> `/customer-statuses/...` es idéntico (permisos `CUSTOMER_STATUSES_*`, código `CUSTOMER_STATUS_*`), **sin `is_won`** y sin `WON_REQUIRES_FINAL`.

### Estado lead de un Person

#### `GET /persons/{id}/lead-status` — `PERSONS_READ` → `SingleResponse[PersonLeadStatusDetail | null]`

`data: null` si la persona no tiene lead activo.

#### `POST /persons/{id}/lead-status` — `LEAD_ACTIVITIES_WRITE` → `201 SingleResponse[PersonLeadStatusDetail]`

**Request** (`LeadStatusCreateRequest`): el lead nace en el estado `is_initial`.
```json
{ "source_campaign_id": null, "reason": "Llegó por WhatsApp" }
```

**Error 400** (no hay estado inicial configurado):
```json
{ "success": false, "detail": "No hay un estado de lead inicial configurado", "code": "NO_INITIAL_LEAD_STATUS" }
```

**Error 409** (ya tiene lead activo):
```json
{ "success": false, "detail": "La persona ya tiene un lead activo", "code": "ALREADY_HAS_ACTIVE_LEAD" }
```

#### `POST /persons/{id}/lead-status/transition` — `LEAD_ACTIVITIES_WRITE` → `SingleResponse[PersonLeadStatusDetail | null]`

**Request** (`LeadStatusTransitionRequest`):
```json
{ "to_lead_status_id": "ls3...", "reason": "Contestó la llamada" }
```

Valida la arista en la matriz; escribe `LeadStatusHistory` + `LeadActivity(STATUS_CHANGE)`. Si el destino es `is_final`, **cierra** el lead (soft-delete de `PersonLeadStatus`) y `data` vuelve `null`.

**Error 400** (sin lead activo):
```json
{ "success": false, "detail": "La persona no tiene un lead activo", "code": "NO_ACTIVE_LEAD" }
```

**Error 400** (arista ausente en la matriz):
```json
{ "success": false, "detail": "Transición de lead no permitida: de 'Nuevo' a 'Interesado'", "code": "LEAD_TRANSITION_NOT_ALLOWED" }
```

**Error 404** (`to_lead_status_id` inexistente) → `LEAD_STATUS_NOT_FOUND`.

#### `POST /persons/{id}/promote-to-customer` — `LEAD_ACTIVITIES_WRITE` → `SingleResponse[PersonCustomerStatusDetail]`

Crea `PersonCustomerStatus(is_initial)` + `CustomerStatusHistory(NULL→initial)`; si hay lead activo en un estado `is_won`, lo cierra; emite `LeadActivity`.

**Error 409** (ya es cliente):
```json
{ "success": false, "detail": "La persona ya es cliente", "code": "ALREADY_CUSTOMER" }
```

#### `GET /persons/{id}/lead-status/history` — `LEAD_STATUS_HISTORY_READ` → `SingleResponse[list[LeadStatusHistoryItem]]`

### Estado customer (análogo)

`GET /persons/{id}/customer-status` (`PERSONS_READ`), `POST /persons/{id}/customer-status/transition` (`LEAD_ACTIVITIES_WRITE`, body `CustomerStatusTransitionRequest`), `GET /persons/{id}/customer-status/history` (`LEAD_STATUS_HISTORY_READ`). No hay `POST .../customer-status` directo: el cliente nace vía `promote-to-customer`.

### Asignación (owner)

#### `GET /persons/{id}/assignment` — `LEAD_ASSIGNMENTS_READ` → `SingleResponse[LeadAssignmentDetail]`

**Error 404** (sin asignación):
```json
{ "success": false, "detail": "La persona no tiene un asesor asignado", "code": "ASSIGNMENT_NOT_FOUND" }
```

#### `PUT /persons/{id}/assignment` — `LEAD_ASSIGNMENTS_WRITE` → `SingleResponse[LeadAssignmentDetail]`

**Request** (`AssignmentRequest`): asignación manual / "asignarme".
```json
{ "advisor_user_id": "u5...", "reason": "Reasignación por carga" }
```

Reasigna: soft-delete fila actual + insert nueva + `LeadActivity(REASSIGNED)`, en una tx.

**Error 400** (advisor inexistente / sin rol ASESOR):
```json
{ "success": false, "detail": "El usuario no tiene el rol ASESOR", "code": "ADVISOR_NOT_ASESOR" }
```
```json
{ "success": false, "detail": "Asesor no encontrado", "code": "ADVISOR_NOT_FOUND" }
```

#### `POST /persons/{id}/assignment/auto` — `LEAD_ASSIGNMENTS_WRITE` → `SingleResponse[LeadAssignmentDetail]`

Round-robin (`SELECT … FOR UPDATE`). Sin body. `assigned_by = NULL` (auto).

**Error 400** (no hay asesor disponible):
```json
{ "success": false, "detail": "No hay asesores disponibles para asignar", "code": "NO_ADVISOR_AVAILABLE" }
```

#### `GET /advisors/active` — `LEAD_ASSIGNMENTS_READ` → lista cruda `list[AdvisorOption]`

Asesores activos (usuarios `active`, no borrados, con rol `ASESOR`) para poblar el dropdown de reasignación (`AssignmentControl`) y el filtro `?advisor_user_id=` del listado de personas. **Pertenece a `crm`, NO a `admin`**: el rol `ASESOR` tiene `LEAD_ASSIGNMENTS_READ` pero **no** `USERS_VIEW`, así que no puede llamar a `/api/v1/admin/users/*`. El service reusa la **misma query de candidatos del round-robin** (usuarios activos con rol `ASESOR`) **sin** `FOR UPDATE`, ordenada por `full_name`. La query "usuarios activos con rol X" se encapsula en un helper **aditivo** `user_repository.list_active_by_role(db, "ASESOR")` en `admin` (cambio aditivo, como `branch_repository.get_by_ids` en staff). `AdvisorOption = { id, full_name }` (el `id` es el `user.id`, lo que espera `advisor_user_id` en `PUT /assignment`).

```json
[
  { "id": "u5...", "full_name": "Ana Torres" },
  { "id": "u8...", "full_name": "Luis Quispe" }
]
```

#### `POST /me/leads/list` — `MY_LEADS_READ` → `PaginatedResponse[MyLeadItem]`

Los leads asignados al asesor logueado (filtra por `lead_assignment.advisor_user_id == CurrentAuth.user.id` + lead activo). Body = `QueryRequest` como `/persons/list`. **Devuelve `MyLeadItem`** (NO `PersonItem`): `{person_id, full_name, primary_identifier, lead_status, last_activity_at, next_follow_up_at}` — bandeja del asesor con el próximo seguimiento denormalizado. Espeja `types/crm.types.ts`.

### LeadActivity (timeline)

#### `POST /persons/{id}/activities/list` — `LEAD_ACTIVITIES_READ` → `SingleResponse[list[ActivityItem]]`

**Request** (`ActivityListRequest`):
```json
{ "activity_type": ["NOTE", "CALL_ATTEMPT"], "date_from": "2026-05-01T00:00:00Z", "date_to": null }
```

#### `POST /persons/{id}/activities` — `LEAD_ACTIVITIES_WRITE` → `201 SingleResponse[ActivityItem]`

**Request** (`ActivityCreate`, solo tipos de asesor):
```json
{ "activity_type": "CALL_ATTEMPT", "content": "No contestó", "outcome": "no_answer" }
```

**Error 422** (tipo no permitido por la API):
```json
{ "success": false, "detail": "Validation failed",
  "errors": [{ "loc": ["body", "activity_type"], "msg": "activity_type not allowed via this endpoint", "type": "value_error" }] }
```

#### `PUT /persons/{id}/activities/{act_id}` — `LEAD_ACTIVITIES_WRITE` → `SingleResponse[ActivityItem]`

Solo `content`/`outcome`/`completed_at`/`scheduled_for`.

**Error 404** (ownership):
```json
{ "success": false, "detail": "Actividad no encontrada", "code": "ACTIVITY_NOT_FOUND" }
```

#### `DELETE /persons/{id}/activities/{act_id}` — `LEAD_ACTIVITIES_WRITE` → `204`

"Borrar" = `active=false` (no hay SoftDelete; desaparece del feed normal).

## Lógica importante (decisiones que el código no expresa solo)

### `person.create` — Person + identifiers nested (sin lead)

```python
# services/person.py — create
async def create(db: AsyncSession, payload: PersonCreate, *, actor_id: str) -> SingleResponse[PersonDetail]:
    now = utc_now()
    person = Person(
        id=generate_uuid(),
        first_name=payload.first_name, last_name=payload.last_name,
        second_last_name=payload.second_last_name,
        document_type=payload.document_type, document_number=payload.document_number,
        birth_date=payload.birth_date, gender=payload.gender,
        address=payload.address, notes=payload.notes, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(person)
    await db.flush()  # materialize person.id for the identifier FKs
    # Inline identifiers — dedup-checked against live rows AND each other.
    for ident in payload.identifiers:
        await _guard_identifier_unique(db, ident.channel_type, ident.identifier)
        db.add(PersonContactIdentifier(
            id=generate_uuid(), person_id=person.id,
            channel_type=ident.channel_type.value, identifier=ident.identifier,
            is_primary=ident.is_primary, verified=ident.verified, active=True,
            created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
        ))
    await db.flush()
    created = await person_repository.get_full(db, person.id)
    audit_users = await user_repository.get_audit_info_map(db, {created.created_by, created.updated_by})
    return SingleResponse(data=_to_detail(created, audit_users))
```

No crea lead. `_guard_identifier_unique` lanza `409 IDENTIFIER_TAKEN` si `get_by_identifier` encuentra una fila viva.

### `person.find_by_identifier_or_create` — orquestación (la llamará `conversations`)

Función de service **sin endpoint público** en el MVP (no hay permiso que mapee; el bot la invoca server-side). `created_by = SYSTEM user id`. Todo en una tx.

```python
# services/person.py
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000002"

async def find_by_identifier_or_create(
    db: AsyncSession, channel_type: ChannelType, identifier: str,
    profile: PersonCreate, *, campaign_id: str | None = None,
) -> Person:
    existing = await person_repository.get_by_identifier(db, channel_type.value, identifier)
    if existing is not None:
        return existing
    now = utc_now()
    # 1) Person + identifier (the incoming handle, marked primary+unverified).
    person = Person(id=generate_uuid(), first_name=profile.first_name, last_name=profile.last_name,
                    active=True, created_by=SYSTEM_USER_ID, created_on=now,
                    updated_by=SYSTEM_USER_ID, updated_on=now)
    db.add(person); await db.flush()
    db.add(PersonContactIdentifier(
        id=generate_uuid(), person_id=person.id, channel_type=channel_type.value,
        identifier=identifier, is_primary=True, verified=False, active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now))
    # 2) PersonLeadStatus(initial) + LeadStatusHistory(NULL→initial).
    initial = await lead_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException("No hay un estado de lead inicial configurado", code="NO_INITIAL_LEAD_STATUS")
    db.add(PersonLeadStatus(
        id=generate_uuid(), person_id=person.id, lead_status_id=initial.id,
        source_campaign_id=campaign_id, entered_status_at=now, last_activity_at=now, active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now))
    db.add(LeadStatusHistory(
        id=generate_uuid(), person_id=person.id, from_lead_status_id=None,
        to_lead_status_id=initial.id, source_campaign_id=campaign_id,
        changed_at=now, changed_by=SYSTEM_USER_ID, reason="Alta automática", active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now))
    # 3) LeadAssignment(round-robin, concurrency-safe).
    advisor_id = await lead_assignment_repository.pick_round_robin_advisor(db)
    if advisor_id is not None:
        db.add(LeadAssignment(
            id=generate_uuid(), person_id=person.id, advisor_user_id=advisor_id,
            assigned_at=now, assigned_by=None, reason="Round-robin automático", active=True,
            created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now))
    # 4) LeadActivity(CAMPAIGN_ATTRIBUTION) if a campaign drove this.
    if campaign_id is not None:
        await lead_activity.log(db, person.id, ActivityType.CAMPAIGN_ATTRIBUTION,
            advisor_user_id=None, payload={"campaign_id": campaign_id}, actor_id=SYSTEM_USER_ID)
    await db.flush()
    return person
```

### `person_lead_status.create` — el lead nace en el `is_initial`

```python
async def create(db, person_id, payload, *, actor_id) -> SingleResponse[PersonLeadStatusDetail]:
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    if await person_lead_status_repository.get_active_for_person(db, person_id) is not None:
        raise ConflictException("La persona ya tiene un lead activo", code="ALREADY_HAS_ACTIVE_LEAD")
    initial = await lead_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException("No hay un estado de lead inicial configurado", code="NO_INITIAL_LEAD_STATUS")
    now = utc_now()
    # insert PersonLeadStatus(initial) + LeadStatusHistory(NULL→initial, source_campaign_id?)
    # ... (audit cols, one tx). Reload via get_full → _to_lead_detail.
```

### `person_lead_status.transition` — matriz + cierre en `is_final`

```python
async def transition(db, person_id, to_id, *, actor_id, reason=None):
    current = await person_lead_status_repository.get_active_for_person(db, person_id)
    if current is None:
        raise BadRequestException("La persona no tiene un lead activo", code="NO_ACTIVE_LEAD")
    target = await lead_status_repository.get_by_id(db, to_id)
    if target is None:
        raise NotFoundException("Estado de lead no encontrado", code="LEAD_STATUS_NOT_FOUND")
    if not await lead_status_transition_repository.is_allowed(db, current.lead_status_id, to_id):
        # detail uses the human names for a friendly message (ES); code in EN.
        raise BadRequestException(
            f"Transición de lead no permitida: de '{current_name}' a '{target.name}'",
            code="LEAD_TRANSITION_NOT_ALLOWED")
    now = utc_now()
    from_id = current.lead_status_id
    # 1) History row.
    db.add(LeadStatusHistory(... from_id, to_id, changed_at=now, changed_by=actor_id, reason ...))
    # 2) STATUS_CHANGE activity (also touches last_activity_at on the lead).
    await lead_activity.log(db, person_id, ActivityType.STATUS_CHANGE,
        advisor_user_id=actor_id, payload={"from": from_id, "to": to_id}, actor_id=actor_id)
    # 3) Apply + maybe close.
    if target.is_final:
        await person_lead_status_repository.soft_delete(db, current)  # close → row gone
        return SingleResponse(data=None)
    current.lead_status_id = to_id
    current.entered_status_at = now
    current.last_activity_at = now
    current.updated_by = actor_id; current.updated_on = now
    return SingleResponse(data=await _to_lead_detail(db, current))
```

Todo en la tx del request (commit al final, rollback si algo lanza).

### `person_customer_status.promote_from_lead`

```python
async def promote_from_lead(db, person_id, *, actor_id, reason=None):
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    if await person_customer_status_repository.get_active_for_person(db, person_id) is not None:
        raise ConflictException("La persona ya es cliente", code="ALREADY_CUSTOMER")
    initial = await customer_status_repository.get_initial(db)
    if initial is None:
        raise BadRequestException("No hay un estado de cliente inicial configurado", code="NO_INITIAL_CUSTOMER_STATUS")
    now = utc_now()
    # 1) PersonCustomerStatus(initial), became_customer_at = entered_status_at = now.
    # 2) CustomerStatusHistory(NULL→initial, changed_by=actor_id).
    # 3) If there's an active lead in an is_won status reachable → close it (soft-delete) + STATUS_CHANGE.
    # 4) LeadActivity (system, advisor=actor) noting the promotion.
    # one tx → reload → _to_customer_detail
```

### `lead_assignment.reassign` + `assign_round_robin` (concurrency-safe)

```python
# reassign (manual / "asignarme")
async def reassign(db, person_id, new_advisor_id, *, actor_id, reason=None):
    person = await person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    advisor = await user_repository.get_by_id(db, new_advisor_id)
    if advisor is None or not advisor.active:
        raise BadRequestException("Asesor no encontrado", code="ADVISOR_NOT_FOUND")
    if not await user_repository.has_role(db, new_advisor_id, "ASESOR"):
        raise BadRequestException("El usuario no tiene el rol ASESOR", code="ADVISOR_NOT_ASESOR")
    now = utc_now()
    current = await lead_assignment_repository.get_active_for_person(db, person_id)
    if current is not None:
        await lead_assignment_repository.soft_delete(db, current)  # free the partial UNIQUE
    db.add(LeadAssignment(id=generate_uuid(), person_id=person_id, advisor_user_id=new_advisor_id,
        assigned_at=now, assigned_by=actor_id, reason=reason, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now))
    await lead_activity.log(db, person_id, ActivityType.REASSIGNED,
        advisor_user_id=new_advisor_id, payload={"by": actor_id, "reason": reason}, actor_id=actor_id)
    await db.flush()
    return SingleResponse(data=await _to_assignment_detail(db, person_id))

# assign_round_robin (auto)
async def assign_round_robin(db, person_id, *, actor_id=None):
    if await lead_assignment_repository.get_active_for_person(db, person_id) is not None:
        return ...  # idempotent no-op: already owned
    advisor_id = await lead_assignment_repository.pick_round_robin_advisor(db)  # SELECT … FOR UPDATE
    if advisor_id is None:
        raise BadRequestException("No hay asesores disponibles para asignar", code="NO_ADVISOR_AVAILABLE")
    # insert LeadAssignment(assigned_by=None) + LeadActivity(REASSIGNED system). one tx.
```

> **Concurrencia**: el `pick_round_robin_advisor` usa `SELECT … FOR UPDATE` sobre el candidato; dos auto-asignaciones simultáneas serializan. El UNIQUE parcial sobre `lead_assignment.person_id` impide dos owners vivos para la misma persona (el segundo insert falla y el service traduce a no-op/retry según el caso).

### `lead_activity.log(...)` — helper interno reusado

```python
async def log(db, person_id, activity_type, *, advisor_user_id, actor_id,
              content=None, scheduled_for=None, completed_at=None, outcome=None, payload=None) -> LeadActivity:
    now = utc_now()
    activity = LeadActivity(
        id=generate_uuid(), person_id=person_id, advisor_user_id=advisor_user_id,
        activity_type=activity_type.value, content=content, scheduled_for=scheduled_for,
        completed_at=completed_at, outcome=outcome.value if outcome else None, payload=payload,
        active=True, created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now)
    db.add(activity)
    # Touch last_activity_at on the active lead (denormalized) if any.
    lead = await person_lead_status_repository.get_active_for_person(db, person_id)
    if lead is not None:
        lead.last_activity_at = now
    return activity
```

Lo reusan `person_lead_status.transition` (`STATUS_CHANGE`), `lead_assignment.reassign`/`assign_round_robin` (`REASSIGNED`), `find_by_identifier_or_create` (`CAMPAIGN_ATTRIBUTION`), y `lead_activity.create` (los tipos de asesor).

### `is_primary` de identifiers (uno por canal)

`contact_identifier.create`/`update` con `is_primary=true`: en la misma tx, `UPDATE person_contact_identifier SET is_primary=false WHERE person_id=? AND channel_type=? AND id<>? AND deleted_at IS NULL`. Dedup proactivo: antes de persistir, `get_by_identifier(channel_type, identifier)` → `409 IDENTIFIER_TAKEN` si choca con una fila viva (de cualquier persona).

### Validaciones de catálogo (1 `is_initial`, `is_won` ⟹ `is_final`)

- En `lead_status.create`/`update`: si `is_initial=true`, `count_initial(exclude_id)` debe ser 0 → si no, `400 MULTIPLE_INITIAL_STATUS`. `is_won ⟹ is_final` (validator Pydantic + re-check en el merge del update) → `400 WON_REQUIRES_FINAL`.
- `delete`: `count_using_status` (live `PersonLeadStatus`) > 0 → `409 LEAD_STATUS_IN_USE` (mismo patrón que `clinic.BRANCH_HAS_ACTIVE_CHILDREN`). El historial NO bloquea el delete (queda como traza; el código no hardcodea catálogos por code, así que un estado borrado no rompe).
- `customer_status`: idéntico **sin** `is_won`/`WON_REQUIRES_FINAL`.

### Denormalización sin N+1 (batch maps, patrón staff/clinic)

`persons.list_paginated` hace `get_paginated` + lookups batch por `IN (person_ids)`: `primary_identifier_map` (el identifier `is_primary` por persona/canal preferido), `lead_status_repository.status_map` + `last_activity_map`, `customer_status_repository.status_map`, `lead_assignment_repository.advisor_map` (resuelto a `UserAuditInfo` vía `user_repository.get_audit_info_map`), y el `get_audit_info_map(created_by/updated_by)`. Cero N+1. `_to_item` recibe esos maps como kwargs (igual que `staff._to_item`). `PersonDetail` se arma desde `get_full` (identifiers/lead/customer/assignment ya cargados con filtro de soft-delete).

### Audit columns con `created_by` / `updated_by`

Cada service que persiste recibe `actor_id` explícito desde el router (`actor: CurrentAuth`). Las operaciones del bot/sistema (`find_by_identifier_or_create`, round-robin auto) usan el `SYSTEM` user (`00000000-0000-0000-0000-000000000002`) como `created_by`/`actor_id`. `changed_by`/`assigned_by` NULL o SYSTEM cuando son automáticos.

## Routers — ejemplos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; `actor: CurrentAuth` aparte cuando se necesita el id para audit; `/active` antes de `/{id}` para que no lo capture la ruta dinámica; `/search` también antes de `/{id}`.

```python
# routers/person.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.person import PersonCreate, PersonDetail, PersonItem, PersonOption, PersonUpdate
from app.modules.crm.services import person as person_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · persons"])

PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]


@router.get("/active", response_model=list[PersonOption],
            dependencies=[Depends(RequirePermission("PERSONS_READ"))])
async def list_active_persons(db: DBSession) -> list[PersonOption]:
    return await person_service.list_active(db)


@router.get("/search", response_model=SingleResponse[list[PersonOption]],
            dependencies=[Depends(RequirePermission("PERSONS_READ"))])
async def search_persons(
    db: DBSession,
    q: Annotated[str | None, Query()] = None,
    channel_type: Annotated[str | None, Query()] = None,
    identifier: Annotated[str | None, Query()] = None,
) -> SingleResponse[list[PersonOption]]:
    return await person_service.search(db, q=q, channel_type=channel_type, identifier=identifier)


@router.post("/list", response_model=PaginatedResponse[PersonItem],
             dependencies=[Depends(RequirePermission("PERSONS_READ"))])
async def list_persons(
    query: QueryRequest, db: DBSession,
    lead_status_id: Annotated[str | None, Query()] = None,
    customer_status_id: Annotated[str | None, Query()] = None,
    advisor_user_id: Annotated[str | None, Query()] = None,
    has_active_lead: Annotated[bool | None, Query()] = None,
) -> PaginatedResponse[PersonItem]:
    return await person_service.list_paginated(
        db, query, lead_status_id=lead_status_id, customer_status_id=customer_status_id,
        advisor_user_id=advisor_user_id, has_active_lead=has_active_lead)


@router.post("", response_model=SingleResponse[PersonDetail], status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(RequirePermission("PERSONS_CREATE"))])
async def create_person(payload: PersonCreate, db: DBSession, actor: CurrentAuth) -> SingleResponse[PersonDetail]:
    return await person_service.create(db, payload, actor_id=actor.id)


@router.get("/{person_id}", response_model=SingleResponse[PersonDetail],
            dependencies=[Depends(RequirePermission("PERSONS_READ"))])
async def get_person(person_id: PersonIdPath, db: DBSession) -> SingleResponse[PersonDetail]:
    return await person_service.get_by_id(db, person_id)


@router.put("/{person_id}", response_model=SingleResponse[PersonDetail],
            dependencies=[Depends(RequirePermission("PERSONS_UPDATE"))])
async def update_person(person_id: PersonIdPath, payload: PersonUpdate, db: DBSession, actor: CurrentAuth) -> SingleResponse[PersonDetail]:
    return await person_service.update(db, person_id, payload, actor_id=actor.id)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(RequirePermission("PERSONS_DELETE"))])
async def delete_person(person_id: PersonIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await person_service.soft_delete(db, person_id, actor_id=actor.id)
```

Lifecycle (estado lead) y `/me/leads` (resuelve el asesor desde `CurrentAuth`):

```python
# routers/lead_lifecycle.py
router = APIRouter(prefix="/persons", tags=["crm · lead lifecycle"])

@router.post("/{person_id}/lead-status/transition",
             response_model=SingleResponse[PersonLeadStatusDetail | None],
             dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))])
async def transition_lead(person_id: PersonIdPath, payload: LeadStatusTransitionRequest,
                          db: DBSession, actor: CurrentAuth) -> SingleResponse[PersonLeadStatusDetail | None]:
    return await person_lead_status_service.transition(
        db, person_id, payload.to_lead_status_id, actor_id=actor.id, reason=payload.reason)

@router.post("/{person_id}/promote-to-customer",
             response_model=SingleResponse[PersonCustomerStatusDetail],
             dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))])
async def promote(person_id: PersonIdPath, db: DBSession, actor: CurrentAuth) -> SingleResponse[PersonCustomerStatusDetail]:
    return await person_customer_status_service.promote_from_lead(db, person_id, actor_id=actor.id)
```

```python
# routers/assignment.py  — note /me/leads/list resolves the advisor from CurrentAuth
me_router = APIRouter(prefix="/me", tags=["crm · me"])

@me_router.post("/leads/list", response_model=PaginatedResponse[PersonItem],
                dependencies=[Depends(RequirePermission("MY_LEADS_READ"))])
async def list_my_leads(query: QueryRequest, db: DBSession, auth: CurrentAuth) -> PaginatedResponse[PersonItem]:
    return await person_service.list_paginated(db, query, advisor_user_id=auth.user.id, has_active_lead=True)
```

> El aggregator incluye tanto el router `/persons/...assignment` como el `me_router` (`/me/leads/...`) desde `routers/assignment.py` (dos `APIRouter` exportados, o uno con ambos prefijos). `/me/leads` NO necesita perfil especial — solo el permiso `MY_LEADS_READ` y filtra por el `user.id` logueado.

## Migrations

Migraciones **manuales y numeradas** (convención medisage). La última aplicada es `0010_staff_doctor_availability`; `crm` encadena desde ahí. Una migración por **grupo cohesivo** (alineada a las fases). **Revision id ≤ 32 chars**. Las 3 columnas forward van **SIN FK** (solo columna + índice). Los índices UNIQUE parciales se escriben con `WHERE deleted_at IS NULL`.

### `0011_crm_person.py` (F1 — person + person_contact_identifier)  · revid `0011_crm_person` (15 chars)

```sql
CREATE TABLE person (
    id               VARCHAR(36) PRIMARY KEY,
    first_name       VARCHAR(80)  NOT NULL,
    last_name        VARCHAR(80)  NOT NULL,
    second_last_name VARCHAR(80),
    document_type    VARCHAR(20),
    document_number  VARCHAR(40),
    birth_date       DATE,
    gender           VARCHAR(20),
    address          VARCHAR(255),
    notes            TEXT,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at       TIMESTAMPTZ,
    created_on       TIMESTAMPTZ NOT NULL,
    created_by       VARCHAR(36) NOT NULL,
    updated_on       TIMESTAMPTZ NOT NULL,
    updated_by       VARCHAR(36) NOT NULL
);
CREATE INDEX ix_person_document_number ON person (document_number);

CREATE TABLE person_contact_identifier (
    id           VARCHAR(36) PRIMARY KEY,
    person_id    VARCHAR(36) NOT NULL REFERENCES person(id),
    channel_type VARCHAR(40) NOT NULL,
    identifier   VARCHAR(255) NOT NULL,
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    verified     BOOLEAN NOT NULL DEFAULT FALSE,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at   TIMESTAMPTZ,
    created_on   TIMESTAMPTZ NOT NULL,
    created_by   VARCHAR(36) NOT NULL,
    updated_on   TIMESTAMPTZ NOT NULL,
    updated_by   VARCHAR(36) NOT NULL
);
CREATE INDEX ix_contact_identifier_person_id ON person_contact_identifier (person_id);
-- Partial UNIQUE: a LIVE (channel_type, identifier) is unique; freed after soft-delete.
CREATE UNIQUE INDEX uq_contact_identifier_channel_value
    ON person_contact_identifier (channel_type, identifier)
    WHERE deleted_at IS NULL;
-- revision = "0011_crm_person"
-- down_revision = "0010_staff_doctor_availability"
```

### `0012_crm_status_catalogs.py` (F2 — catálogos + matriz)  · revid `0012_crm_status_catalogs` (24 chars)

```sql
CREATE TABLE lead_status (
    id            VARCHAR(36) PRIMARY KEY,
    code          VARCHAR(40)  NOT NULL UNIQUE,
    name          VARCHAR(120) NOT NULL,
    description   VARCHAR(500),
    color         VARCHAR(20),
    is_initial    BOOLEAN NOT NULL DEFAULT FALSE,
    is_final      BOOLEAN NOT NULL DEFAULT FALSE,
    is_won        BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL DEFAULT 0,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at    TIMESTAMPTZ,
    created_on    TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on    TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);

CREATE TABLE customer_status (  -- same minus is_won
    id            VARCHAR(36) PRIMARY KEY,
    code          VARCHAR(40)  NOT NULL UNIQUE,
    name          VARCHAR(120) NOT NULL,
    description   VARCHAR(500),
    color         VARCHAR(20),
    is_initial    BOOLEAN NOT NULL DEFAULT FALSE,
    is_final      BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL DEFAULT 0,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at    TIMESTAMPTZ,
    created_on    TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on    TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);

-- Transition matrices (ADR-008). No deleted_at (config; active toggles).
CREATE TABLE lead_status_transition (
    id                  VARCHAR(36) PRIMARY KEY,
    from_lead_status_id VARCHAR(36) NOT NULL REFERENCES lead_status(id),
    to_lead_status_id   VARCHAR(36) NOT NULL REFERENCES lead_status(id),
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL,
    CONSTRAINT uq_lead_status_transition_from_to UNIQUE (from_lead_status_id, to_lead_status_id)
);
CREATE INDEX ix_lead_status_transition_from ON lead_status_transition (from_lead_status_id);

CREATE TABLE customer_status_transition (  -- analogous to customer_status
    id                      VARCHAR(36) PRIMARY KEY,
    from_customer_status_id VARCHAR(36) NOT NULL REFERENCES customer_status(id),
    to_customer_status_id   VARCHAR(36) NOT NULL REFERENCES customer_status(id),
    active                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL,
    CONSTRAINT uq_customer_status_transition_from_to UNIQUE (from_customer_status_id, to_customer_status_id)
);
CREATE INDEX ix_customer_status_transition_from ON customer_status_transition (from_customer_status_id);
-- revision = "0012_crm_status_catalogs"
-- down_revision = "0011_crm_person"
```

### `0013_crm_lead_lifecycle.py` (F3 — lead status + history + assignment + activity)  · revid `0013_crm_lead_lifecycle` (23 chars)

```sql
CREATE TABLE person_lead_status (
    id                 VARCHAR(36) PRIMARY KEY,
    person_id          VARCHAR(36) NOT NULL REFERENCES person(id),
    lead_status_id     VARCHAR(36) NOT NULL REFERENCES lead_status(id),
    source_campaign_id VARCHAR(36),  -- forward FK (ADR-009): NO constraint, index only
    entered_status_at  TIMESTAMPTZ NOT NULL,
    last_activity_at   TIMESTAMPTZ,
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at         TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE UNIQUE INDEX uq_person_lead_status_person ON person_lead_status (person_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_person_lead_status_campaign ON person_lead_status (source_campaign_id);

CREATE TABLE lead_status_history (   -- NO deleted_at (immutable audit)
    id                 VARCHAR(36) PRIMARY KEY,
    person_id          VARCHAR(36) NOT NULL REFERENCES person(id),
    from_lead_status_id VARCHAR(36) REFERENCES lead_status(id),
    to_lead_status_id   VARCHAR(36) NOT NULL REFERENCES lead_status(id),
    source_campaign_id  VARCHAR(36),  -- forward FK (ADR-009): NO constraint, index only
    changed_at TIMESTAMPTZ NOT NULL,
    changed_by VARCHAR(36),
    reason     VARCHAR(255),
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_lead_status_history_person ON lead_status_history (person_id);
CREATE INDEX ix_lead_status_history_campaign ON lead_status_history (source_campaign_id);

CREATE TABLE lead_assignment (
    id              VARCHAR(36) PRIMARY KEY,
    person_id       VARCHAR(36) NOT NULL REFERENCES person(id),
    advisor_user_id VARCHAR(36) NOT NULL REFERENCES "user"(id),
    assigned_at     TIMESTAMPTZ NOT NULL,
    assigned_by     VARCHAR(36),  -- logical FK (NULL = round-robin auto / SYSTEM)
    reason          VARCHAR(255),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at      TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE UNIQUE INDEX uq_lead_assignment_person ON lead_assignment (person_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_lead_assignment_advisor ON lead_assignment (advisor_user_id);

CREATE TABLE lead_activity (   -- NO deleted_at ("delete" = active=false)
    id                      VARCHAR(36) PRIMARY KEY,
    person_id               VARCHAR(36) NOT NULL REFERENCES person(id),
    advisor_user_id         VARCHAR(36) REFERENCES "user"(id),
    activity_type           VARCHAR(40) NOT NULL,
    content                 TEXT,
    scheduled_for           TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    outcome                 VARCHAR(40),
    payload                 JSONB,
    related_appointment_id  VARCHAR(36),  -- forward FK (ADR-009): NO constraint, index only
    related_conversation_id VARCHAR(36),  -- forward FK (ADR-009): NO constraint, index only
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_lead_activity_person ON lead_activity (person_id);
CREATE INDEX ix_lead_activity_appointment ON lead_activity (related_appointment_id);
CREATE INDEX ix_lead_activity_conversation ON lead_activity (related_conversation_id);
-- revision = "0013_crm_lead_lifecycle"
-- down_revision = "0012_crm_status_catalogs"
```

> `"user"` va entre comillas: `user` es palabra reservada en Postgres. Las columnas forward (`source_campaign_id`, `related_appointment_id`, `related_conversation_id`) son `VARCHAR(36)` + índice **sin** `REFERENCES` — el módulo dueño agrega `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` cuando cree su tabla (ADR-009). El `lead_activity` se crea en F3 (lo necesitan `STATUS_CHANGE`/`REASSIGNED`); F5 solo lo enriquece con más tipos, sin migración.

### `0014_crm_customer_lifecycle.py` (F4 — customer status + history)  · revid `0014_crm_customer_lifecycle` (27 chars)

```sql
CREATE TABLE person_customer_status (
    id                 VARCHAR(36) PRIMARY KEY,
    person_id          VARCHAR(36) NOT NULL REFERENCES person(id),
    customer_status_id VARCHAR(36) NOT NULL REFERENCES customer_status(id),
    became_customer_at TIMESTAMPTZ NOT NULL,
    entered_status_at  TIMESTAMPTZ NOT NULL,
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at         TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE UNIQUE INDEX uq_person_customer_status_person ON person_customer_status (person_id) WHERE deleted_at IS NULL;

CREATE TABLE customer_status_history (   -- NO deleted_at (immutable)
    id                      VARCHAR(36) PRIMARY KEY,
    person_id               VARCHAR(36) NOT NULL REFERENCES person(id),
    from_customer_status_id VARCHAR(36) REFERENCES customer_status(id),
    to_customer_status_id   VARCHAR(36) NOT NULL REFERENCES customer_status(id),
    changed_at TIMESTAMPTZ NOT NULL,
    changed_by VARCHAR(36),
    reason     VARCHAR(255),
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_customer_status_history_person ON customer_status_history (person_id);
-- revision = "0014_crm_customer_lifecycle"
-- down_revision = "0013_crm_lead_lifecycle"
```

**Cadena de revids** (todos ≤32): `0011_crm_person` (15) → `0012_crm_status_catalogs` (24) → `0013_crm_lead_lifecycle` (23) → `0014_crm_customer_lifecycle` (27). F0 y F5 no llevan migración (F0 = solo seed; F5 = las tablas ya existen).

## Seed

Los **15 permisos** de `crm` ya están consolidados en [`_seed-and-roles.md`](../_seed-and-roles.md) (`MENU-CRM`, `PERSONS_READ/CREATE/UPDATE/DELETE`, `LEAD_STATUSES_READ/WRITE`, `CUSTOMER_STATUSES_READ/WRITE`, `LEAD_ASSIGNMENTS_READ/WRITE`, `LEAD_ACTIVITIES_READ/WRITE`, `LEAD_STATUS_HISTORY_READ`, `MY_LEADS_READ`; `module="CRM"`). **NO redefinir** — solo agregarlos a `SEED_PERMISSIONS` si aún no están. El subset de `ASESOR` (corazón del trabajo: PERSONS_*, LEAD_*, MY_LEADS_READ) y de `DOCTOR` (`PERSONS_READ`) también están canónicos ahí — el helper `_seed_role` los filtra por código (idempotente, a prueba de orden de módulos).

### F0 introduce el user/role `SYSTEM` (diferido desde staff)

`staff` difirió el `SYSTEM`; `crm` lo necesita (`find_by_identifier_or_create` y round-robin auto atribuyen `created_by = SYSTEM`). Usar los helpers ya documentados en [`_seed-and-roles.md`](../_seed-and-roles.md#patches-sugeridos-a-appcoreseedpy):

- `_seed_role(db, actor_id, "SYSTEM", "User técnico no autenticable", set(), perms)` — role con **permisos vacíos**.
- `_seed_system_user(db, actor_id)` — user `00000000-0000-0000-0000-000000000002`, `email="system@medisage.internal"`, `active=false`, password no usable, `roles=[]`. El backend nunca resuelve `CurrentAuth` a este user (el `active=false` lo impide en el login normal).

### `_seed_lead_statuses` (7) / `_seed_customer_statuses` (5) — idempotentes (por `code`)

```python
LEAD_STATUS_SEED: list[tuple] = [
    # (code, name, color, is_initial, is_final, is_won, display_order)
    ("NUEVO",                "Nuevo",                "#9CA3AF", True,  False, False, 10),
    ("INTENTANDO_CONTACTAR", "Intentando contactar", "#F59E0B", False, False, False, 20),
    ("CONTACTADO",           "Contactado",           "#3B82F6", False, False, False, 30),
    ("INTERESADO",           "Interesado",           "#06B6D4", False, False, False, 40),
    ("EVALUANDO",            "Evaluando",            "#8B5CF6", False, False, False, 50),
    ("CITA_AGENDADA",        "Cita agendada",        "#22C55E", False, True,  True,  60),
    ("NO_INTERESADO",        "No interesado",        "#EF4444", False, True,  False, 70),
]

CUSTOMER_STATUS_SEED: list[tuple] = [
    # (code, name, color, is_initial, is_final, display_order)
    ("ACTIVO",         "Activo",         "#22C55E", True,  False, 10),
    ("EN_TRATAMIENTO", "En tratamiento", "#06B6D4", False, False, 20),
    ("COMPLETADO",     "Completado",     "#8B5CF6", False, False, 30),
    ("INACTIVO",       "Inactivo",       "#9CA3AF", False, False, 40),
    ("PERDIDO",        "Perdido",        "#EF4444", False, True,  50),
]
```

Cada `_seed_<catalog>_statuses(db, actor_id)` busca por `code`; inserta los faltantes, no pisa los existentes (la clínica los puede editar después). Se invocan en `seed()` tras los roles, como ya prevé [`_seed-and-roles.md`](../_seed-and-roles.md#patches-sugeridos-a-appcoreseedpy) (`await _seed_lead_statuses(db, actor_id)` / `await _seed_customer_statuses(db, actor_id)`).

### `_seed_lead_transition_matrix` / `_seed_customer_transition_matrix` — matriz base (§Matriz, seed editable)

Tras seedear los estados, insertar las aristas base (resolviendo los `code` a `id`). Idempotente: solo crea aristas faltantes.

**Lead** (a partir de los 7 estados; `CITA_AGENDADA` y `NO_INTERESADO` terminales, sin salida):
```python
LEAD_TRANSITIONS: list[tuple[str, str]] = [
    ("NUEVO", "INTENTANDO_CONTACTAR"), ("NUEVO", "NO_INTERESADO"),
    ("INTENTANDO_CONTACTAR", "CONTACTADO"), ("INTENTANDO_CONTACTAR", "NO_INTERESADO"),
    ("CONTACTADO", "INTERESADO"), ("CONTACTADO", "INTENTANDO_CONTACTAR"), ("CONTACTADO", "NO_INTERESADO"),
    ("INTERESADO", "EVALUANDO"), ("INTERESADO", "NO_INTERESADO"),
    ("EVALUANDO", "CITA_AGENDADA"), ("EVALUANDO", "INTERESADO"), ("EVALUANDO", "NO_INTERESADO"),
]
```

**Customer** (permisivo — no-finales entre sí + hacia finales; `PERDIDO` terminal):
```python
CUSTOMER_TRANSITIONS: list[tuple[str, str]] = [
    ("ACTIVO", "EN_TRATAMIENTO"), ("ACTIVO", "COMPLETADO"),
    ("EN_TRATAMIENTO", "ACTIVO"), ("EN_TRATAMIENTO", "COMPLETADO"),
    ("COMPLETADO", "ACTIVO"), ("COMPLETADO", "EN_TRATAMIENTO"),
    ("ACTIVO", "INACTIVO"), ("EN_TRATAMIENTO", "INACTIVO"), ("COMPLETADO", "INACTIVO"),
    ("ACTIVO", "PERDIDO"), ("EN_TRATAMIENTO", "PERDIDO"), ("COMPLETADO", "PERDIDO"), ("INACTIVO", "PERDIDO"),
    ("INACTIVO", "ACTIVO"),  # reactivar
]
```

> `promote-to-customer` **no** es una arista del grafo lead (es una operación aparte que abre el hilo customer).

## Checklist de implementación (mapeado a fases F0–F5)

### F0 — Prep (sin migración; solo seed + skeleton)
- [ ] Agregar los 15 permisos `CRM` a `app/core/seed.py:SEED_PERMISSIONS` (ya canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md); no redefinir).
- [ ] **Introducir el `SYSTEM` user (`active=false`) + role `SYSTEM` (perms vacíos)** vía `_seed_system_user`/`_seed_role` (diferido desde staff).
- [ ] Verificar que `_seed_role` aplique los subsets `ASESOR`/`DOCTOR` ya con los códigos CRM (el filtro por código los toma al existir el permiso).
- [ ] Crear el skeleton `backend/app/modules/crm/{enums,models,schemas,repositories,services,routers}/` (`enums.py` con `ChannelType`/`ActivityType` completo/`ActivityOutcome`).
- [ ] Registrar el módulo en `app/modules/__init__.py` (`from app.modules import admin, catalog, clinic, crm, staff`).
- [ ] Incluir el aggregator router en `app/main.py` (`prefix="/crm"`).
- [ ] (Frontend F0) nav grupo "CRM" (`MENU-CRM`) + iconos; `endpoints.ts` (bloque CRM); `types/crm.types.ts` — ver [`frontend.md`](frontend.md).
- [ ] Smoke test: login admin → el JWT contiene los 15 permisos CRM; el user `system@medisage.internal` existe con `active=false`.

### F1 — Person + Identifiers (migración `0011_crm_person`)
- [ ] `models/person.py` + `models/person_contact_identifier.py` (UNIQUE parcial `(channel_type, identifier) WHERE deleted_at IS NULL`) + migración `0011_crm_person` (`down_revision="0010_staff_doctor_availability"`).
- [ ] `schemas/person.py` (`PersonCreate` con identifiers nested + validator no-dupes/1-primary-por-canal, `PersonUpdate`, `PersonItem` denormalizado, `PersonDetail`, `PersonOption`) + `schemas/contact_identifier.py`.
- [ ] `repositories/person.py`: `ALLOWED_FIELDS` (solo columnas reales — lección cd10c78), `get_by_identifier`, `get_full` (eager identifiers/lead/customer/assignment con `with_loader_criteria`), `search`, `list_active`, batch maps.
- [ ] `services/person.py`: `create` (Person + identifiers nested, dedup), `update`, `soft_delete`, `list_paginated` (deep-link `?lead_status_id=`/`?advisor_user_id=`/`?has_active_lead=` → EXISTS), `search`, `find_by_identifier_or_create` (esqueleto; se completa en F5) + `services/contact_identifier.py` (dedup `IDENTIFIER_TAKEN`, `is_primary` único por canal).
- [ ] `routers/person.py` (CRUD + `/active` + `/search` antes de `/{id}`) + `routers/contact_identifier.py` (anidado).
- [ ] (Frontend F1) `/crm/personas` lista + drawer + detalle (tabs Datos/Identificadores/Auditoría; Lead/Cliente/Actividad placeholders) — ver [`ui.md`](ui.md).
- [ ] Test dedup: dos identifiers `(whatsapp, +51...)` vivos → `409 IDENTIFIER_TAKEN`; soft-delete uno → el otro se puede crear.
- [ ] Test ownership: `PUT`/`DELETE` de un identifier de otra persona → `404 IDENTIFIER_NOT_FOUND`.
- [ ] Test `search`: `(channel_type, identifier)` exacto retorna la persona; `q` hace ILIKE; sin match = lista vacía (no 404).

### F2 — Catálogos + matriz (migración `0012_crm_status_catalogs`)
- [ ] `models/lead_status.py`, `customer_status.py`, `lead_status_transition.py`, `customer_status_transition.py` + migración `0012_crm_status_catalogs` (`down_revision="0011_crm_person"`).
- [ ] `schemas/lead_status.py` (validators `WON_REQUIRES_FINAL`; `StatusTransitionUpdate {to_ids}`) + `schemas/customer_status.py` (sin `is_won`).
- [ ] `repositories/lead_status.py` (`get_by_code`, `get_initial`, `count_initial`, `count_using_status`) + `lead_status_transition.py` (`is_allowed`, `list_outgoing`, `replace_outgoing`); análogos customer.
- [ ] `services/lead_status.py`/`customer_status.py`: CRUD + validaciones (1 `is_initial` → `MULTIPLE_INITIAL_STATUS`; `is_won⟹is_final`; delete guard `*_IN_USE`), matriz (`GET`/`PUT /{id}/transitions`).
- [ ] `_seed_lead_statuses` (7) + `_seed_customer_statuses` (5) + `_seed_lead_transition_matrix`/`_seed_customer_transition_matrix` (base) — idempotentes por `code`.
- [ ] `routers/lead_status.py`/`customer_status.py` (CRUD + `/active` + `/{id}/transitions`).
- [ ] (Frontend F2) `/crm/estados-lead` + `/crm/estados-cliente` con editor de matriz — ver [`ui.md`](ui.md).
- [ ] Test seed: 7 lead + 5 customer; exactamente 1 `is_initial` por catálogo; matriz base presente.
- [ ] Test `WON_REQUIRES_FINAL` (400), `MULTIPLE_INITIAL_STATUS` (400), `LEAD_STATUS_IN_USE` (409 al borrar con leads).

### F3 — Lead lifecycle (migración `0013_crm_lead_lifecycle`)
- [ ] `models/person_lead_status.py` (UNIQUE parcial), `lead_status_history.py` (sin SD), `lead_assignment.py` (UNIQUE parcial), `lead_activity.py` (sin SD, forward FKs) + migración `0013_crm_lead_lifecycle` (`down_revision="0012_crm_status_catalogs"`).
- [ ] `schemas/lead_lifecycle.py` + `assignment.py` + `activity.py` (con `ADVISOR_ACTIVITY_TYPES`).
- [ ] `repositories/person_lead_status.py` (`get_active_for_person`, `status_map`, `last_activity_map`), `lead_assignment.py` (`pick_round_robin_advisor` con `SELECT … FOR UPDATE`), `lead_activity.py` (`list_for_person`), `lead_status_history.py`.
- [ ] `services/person_lead_status.py` (`create`, `transition` con matriz + cierre `is_final`), `lead_assignment.py` (`reassign` con `ADVISOR_NOT_ASESOR`, `assign_round_robin` concurrency-safe), `lead_activity.py` (`log` helper + CRUD timeline básico STATUS_CHANGE/REASSIGNED).
- [ ] `routers/lead_lifecycle.py` (status/transition/history), `assignment.py` (assignment + `/auto` + `/advisors/active` + `/me/leads/list`), `activity.py`.
- [ ] `services/lead_assignment.py`: `list_advisors` (reusa la query de candidatos del round-robin sin `FOR UPDATE`, orden `full_name`) → `GET /advisors/active`; agregar `user_repository.list_active_by_role(db, "ASESOR")` a `admin` (aditivo).
- [ ] (Frontend F3) tab Lead + `AssignmentControl` + `/crm/mis-leads` — ver [`ui.md`](ui.md).
- [ ] Test transition: arista válida cambia estado + escribe history + STATUS_CHANGE; arista ausente → `400 LEAD_TRANSITION_NOT_ALLOWED`; `is_final` cierra (soft-delete) y `data=null`.
- [ ] Test `NO_ACTIVE_LEAD`/`ALREADY_HAS_ACTIVE_LEAD`/`NO_INITIAL_LEAD_STATUS`.
- [ ] Test assignment: manual con user sin rol ASESOR → `400 ADVISOR_NOT_ASESOR`; round-robin sin asesores → `400 NO_ADVISOR_AVAILABLE`; reasignar soft-deletea la anterior + REASSIGNED.
- [ ] Test `/me/leads/list` filtra por el `user.id` logueado + lead activo.

### F4 — Customer lifecycle (migración `0014_crm_customer_lifecycle`)
- [ ] `models/person_customer_status.py` (UNIQUE parcial) + `customer_status_history.py` (sin SD) + migración `0014_crm_customer_lifecycle` (`down_revision="0013_crm_lead_lifecycle"`).
- [ ] `schemas/customer_lifecycle.py` + `repositories/person_customer_status.py`/`customer_status_history.py`.
- [ ] `services/person_customer_status.py`: `promote_from_lead` (crea customer inicial + history; cierra lead `is_won` si aplica; emite activity; `ALREADY_CUSTOMER`), `transition` (matriz customer).
- [ ] `routers/customer_lifecycle.py` (`GET customer-status`, `transition`, `history`) + wire de `promote-to-customer` en `lead_lifecycle`.
- [ ] (Frontend F4) tab Cliente — ver [`ui.md`](ui.md).
- [ ] Test promote: lead `is_won` → crea customer `is_initial` + cierra lead; doble promote → `409 ALREADY_CUSTOMER`.
- [ ] Test transition customer: matriz permisiva (ACTIVO↔EN_TRATAMIENTO↔COMPLETADO; → INACTIVO/PERDIDO).

### F5 — Timeline + orquestación (sin migración; tablas ya existen)
- [ ] `lead_activity` rico: `create` valida `ADVISOR_ACTIVITY_TYPES` (NOTE/CALL_ATTEMPT/FOLLOW_UP_*), `update` (solo content/outcome/completed_at/scheduled_for), `delete` (`active=false`), `list` con filtros tipados.
- [ ] `find_by_identifier_or_create` completo (Person + identifier + PersonLeadStatus initial + history + round-robin assignment + CAMPAIGN_ATTRIBUTION; `created_by=SYSTEM`) — función de service, sin endpoint público.
- [ ] Confirmar enum `ActivityType` completo (cross-module presentes, emisión diferida a conversations/scheduling).
- [ ] (Frontend F5) timeline UI pesado (composer/chips/day-groups) — ver [`ui.md`](ui.md).
- [ ] Test timeline: crear NOTE/CALL_ATTEMPT (outcome)/FOLLOW_UP_SCHEDULED (requiere scheduled_for); tipo no-asesor → 422; `DELETE` = `active=false` (desaparece del feed); `log` toca `last_activity_at` del lead activo.
- [ ] Test `find_by_identifier_or_create`: identifier nuevo → crea toda la cadena con `created_by=SYSTEM`; identifier existente → retorna la Person sin duplicar.
