# Módulo `staff` — Backend deep-dive

> **Última actualización**: 2026-05-29
> **Audiencia**: developer implementando `backend/app/modules/staff/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), la ficha de clínica [`../clinic/backend.md`](../clinic/backend.md) (molde directo de este doc — `staff` referencia `clinic.Branch`/`clinic.Office` por FK y M:N), la de catálogo [`../catalog/backend.md`](../catalog/backend.md) (`staff` referencia `catalog.Vertical` por M:N) y el módulo `admin` (`Doctor` es 1:1 con `admin.User` y la creación NESTED espeja `admin.user.create`).

> **Contrato autoritativo**: este doc respeta la spec compartida de `staff` (entidades, campos, endpoints, permisos, códigos de error). Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc.

> **Cambio respecto al overview previo** (`docs/modules/staff.md`, ahora deprecado): el modelo de disponibilidad **NO** es `Pattern` (semanal recurrente) + `Override` (excepción `is_available`). Es **una sola entidad `DoctorAvailability`** de **bloques concretos por fecha** (sin `day_of_week`, sin recurrencia, sin flag `is_available`). Razón confirmada por el usuario: los doctores no tienen horario fijo — cada mes (re)definen sus horarios concretos. "No disponible" = no hay bloque; "vacaciones" = sin bloques; "extra" = agregar bloque. `ADR-002` (doctor 1:1 user) sigue vigente; `ADR-006` (slots híbridos) se actualizará aparte para reflejar bloques concretos en vez de pattern+override.

> **Convenciones heredadas de `clinic`/`catalog` shipped** (repetidas aquí para que este doc se lea solo):
>
> 1. **`PUT` para updates completos** (no `PATCH`). El overview viejo listaba `PATCH /doctors/{id}` y `PATCH /me/doctor` — quedan **deprecados**.
> 2. **`/active` para dropdowns** (no `/options`). El overview viejo listaba `/doctors/options` — **deprecado**. `/active` devuelve **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`), igual que `clinic`/`catalog`.
> 3. Services = **módulos de funciones** (no clases); excepciones de dominio (no `HTTPException`); `actor_id` explícito desde el router; reload-via-`get_full` tras create/update (relaciones `lazy="raise"`); `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` como whitelist.
> 4. **Mensajes `detail` de dominio en español, `code` en inglés**, mensajes de validators Pydantic en inglés (el front re-valida con Zod).

## Estructura de archivos a crear

```
backend/app/modules/staff/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── associations.py            # doctor_branch (M:N → clinic.branch) + doctor_vertical (M:N → catalog.vertical)
│   ├── doctor.py
│   └── doctor_availability.py
├── schemas/
│   ├── __init__.py
│   ├── doctor.py
│   └── doctor_availability.py
├── repositories/
│   ├── __init__.py
│   ├── doctor.py
│   └── doctor_availability.py
├── services/
│   ├── __init__.py
│   ├── doctor.py
│   ├── doctor_availability.py
│   └── me.py                      # resuelve el doctor desde CurrentAuth (self-service /me)
└── routers/
    ├── __init__.py                # aggregator: prefix="/staff"
    ├── doctor.py                  # /doctors/*
    ├── doctor_availability.py     # /doctors/{id}/availability/*
    └── me.py                      # /me/doctor + /me/availability/*
```

**Sí hay `models/associations.py`** (igual que `clinic`): `doctor_branch` y `doctor_vertical` son propiedad de `staff` — referencian `clinic.branch.id` y `catalog.vertical.id` pero las tablas de asociación viven aquí. Sigue la convención del template (`admin/models/associations.py` aloja `user_role`, `role_permission`, `user_permission`; `clinic/models/associations.py` aloja `office_vertical`).

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean):

```python
from app.modules import admin, catalog, clinic, staff  # noqa: F401
```

Y registrar el aggregator en `app/main.py` (un solo `include_router`, como `clinic`):

```python
from app.modules.staff.routers import router as staff_router

app.include_router(staff_router)  # prefix="/api/v1" + "/staff" interno
```

El aggregator `routers/__init__.py` replica el patrón de `clinic/routers/__init__.py`:

```python
"""
Aggregates the staff sub-routers under one prefix. `main.py` includes this
`router` once.
"""

from fastapi import APIRouter

from app.modules.staff.routers.doctor import router as doctor_router
from app.modules.staff.routers.doctor_availability import router as availability_router
from app.modules.staff.routers.me import router as me_router

router = APIRouter(prefix="/staff")
router.include_router(doctor_router)
# Nested under /doctors/{doctor_id}/availability/... (phase F2).
router.include_router(availability_router)
# Self-service for the logged-in doctor (phase F3): /me/doctor + /me/availability/*.
router.include_router(me_router)

__all__ = ["router"]
```

## Models — SQLAlchemy 2.0

### `models/associations.py` — tablas M:N `doctor_branch` y `doctor_vertical`

```python
"""
Many-to-many association tables for the staff module. Kept in a single file so
SQLAlchemy sees them before the related models import (template convention —
admin/models/associations.py and clinic/models/associations.py do the same).

`doctor_branch` links a Doctor to the clinic Branches where they practice.
`doctor_vertical` links a Doctor to the catalog Verticals they cover.

Same FK policy as clinic.office_vertical: the CHILD side (doctor_id) is
ON DELETE CASCADE — soft-deleting a doctor is the normal path (filtered at
query time), but a hard-delete migration of a doctor may clean up its
association rows without cross-module coordination. The PARENT side
(branch_id / vertical_id) is RESTRICT (default, no ondelete) — a branch or a
vertical is deleted from its OWN module; the FK is the backstop that blocks a
hard-delete while it is still attached. The normal soft-delete of a
branch/vertical does NOT touch these tables: the rows stay and are filtered out
when hydrating (see the repository).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

doctor_branch = Table(
    "doctor_branch",
    Base.metadata,
    Column(
        "doctor_id",
        String(36),
        ForeignKey("doctor.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "branch_id",
        String(36),
        ForeignKey("branch.id"),  # RESTRICT — no ondelete cascade to clinic
        primary_key=True,
    ),
)

doctor_vertical = Table(
    "doctor_vertical",
    Base.metadata,
    Column(
        "doctor_id",
        String(36),
        ForeignKey("doctor.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "vertical_id",
        String(36),
        ForeignKey("vertical.id"),  # RESTRICT — no ondelete cascade to catalog
        primary_key=True,
    ),
)
```

**Por qué `doctor_id` es `CASCADE` pero `branch_id`/`vertical_id` son `RESTRICT`**: idéntica lógica a `clinic.office_vertical`. El soft-delete del doctor (path normal) no toca estas tablas — las filas quedan y se filtran al hidratar (`branches_count`/`verticals_count` y `DoctorDetail.branches`/`.verticals` filtran `deleted_at IS NULL` del padre). El `RESTRICT` solo actúa como backstop ante un hard-delete de un branch/vertical aún asociado. Esto evita acoplar el delete guard de `clinic`/`catalog` a `staff`.

### `models/doctor.py`

```python
"""
Doctor = the professional profile of a clinician, 1:1 with admin.User (ADR-002).
The User holds identity/auth (email, name, password, role); Doctor holds
professional data (CMP code, bio, photo, signature, slot grain) and the M:N
links to the Branches where they practice and the Verticals they cover.

`user_id` is UNIQUE and immutable after creation — moving a profile to another
identity is not a supported operation. `slot_duration_min` is the minimum
schedulable unit of the doctor's calendar; scheduling rounds product durations
up to a multiple of it (see ADR-006 / README "slot_duration"). Soft-deleting a
Doctor does NOT touch the User (ADR-002): to block platform access set
`user.active = false` from the admin module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.vertical import Vertical
    from app.modules.clinic.models.branch import Branch
    from app.modules.staff.models.doctor_availability import DoctorAvailability


class Doctor(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "doctor"

    # 1:1 with admin.User. UNIQUE enforces the one-profile-per-user rule at the
    # DB level; immutable post-creation (DoctorUpdate doesn't declare it).
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), unique=True, nullable=False, index=True
    )
    # Colegio Médico del Perú code (or homolog). Nullable for non-physicians
    # (estheticians, kinesiologists). Indexed for future official reporting.
    cmp_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Calendar grain for scheduling. Default 30 min.
    slot_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # The User this profile extends. `lazy="raise"` — loaded explicitly with
    # selectinload when a detail/list view needs full_name/email.
    user: Mapped[User] = relationship(lazy="raise")  # type: ignore[name-defined]

    # M:N with clinic.Branch (sedes where the doctor practices). `lazy="raise"`:
    # loaded with selectinload + a deleted_at filter in the repository.
    branches: Mapped[list[Branch]] = relationship(
        secondary=doctor_branch, lazy="raise"
    )
    # M:N with catalog.Vertical (verticals the doctor covers). Same strategy.
    verticals: Mapped[list[Vertical]] = relationship(
        secondary=doctor_vertical, lazy="raise"
    )

    # Children. `lazy="raise"` — availability blocks are loaded per-doctor on
    # demand (their own endpoints), never eagerly with the doctor list.
    availability: Mapped[list[DoctorAvailability]] = relationship(
        back_populates="doctor", lazy="raise"
    )
```

> **Nota M:N sin `back_populates`**: `doctor_branch`/`doctor_vertical` son *uni-direccionales* desde `staff` (igual que `clinic.office_vertical`). `clinic.Branch` y `catalog.Vertical` **NO** declaran `doctors` ni conocen estas asociaciones — eso mantiene `clinic`/`catalog` desacoplados de `staff` (`staff` depende de ellos, no al revés). La relación `Doctor.user` también es uni-direccional: `admin.User` no declara `doctor` (mantiene `admin` agnóstico de los módulos de dominio).

### `models/doctor_availability.py`

```python
"""
DoctorAvailability = ONE concrete block of availability for a doctor on a
specific calendar date, in a specific (branch, office). Replaces the previous
Pattern+Override model: there is NO day_of_week, NO recurrence, NO is_available
flag. "Not available" = no block; "vacation" = no blocks; "extra slot" = add a
block.

`date` is a calendar date (no time); `opens_at`/`closes_at` are naive `time`
(no TZ) interpreted in `branch.timezone`. CHECK closes_at > opens_at: a block
never crosses midnight (model that as two blocks on two dates). Office closures
stay in clinic.OfficeClosure — scheduling subtracts them; staff does not.
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.staff.models.doctor import Doctor


class DoctorAvailability(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "doctor_availability"
    __table_args__ = (
        CheckConstraint(
            "closes_at > opens_at",
            name="ck_doctor_availability_closes_after_opens",
        ),
    )

    doctor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("doctor.id"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(String(36), ForeignKey("branch.id"), nullable=False)
    office_id: Mapped[str] = mapped_column(String(36), ForeignKey("office.id"), nullable=False)
    # Concrete calendar date; the local hours are interpreted in branch.timezone.
    date: Mapped[date] = mapped_column(Date, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    closes_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)

    doctor: Mapped[Doctor] = relationship(back_populates="availability", lazy="raise")
```

> **Índices**: `ix_doctor_availability_doctor_id` (vía `index=True` en `doctor_id`) cubre el filtro base de "los bloques de un doctor". La consulta de rango (`GET ?from=&to=`) filtra `doctor_id` + `date` BETWEEN — un índice compuesto opcional `ix_doctor_availability_doctor_id_date (doctor_id, date)` lo acelera; se declara en la migración (ver abajo) como índice no-único.

### `models/__init__.py`

```python
"""
Importing models here ensures SQLAlchemy registers them on `Base.metadata`
before Alembic reads the schema. Import associations first so the M:N tables
exist before Doctor references them.
"""

from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.modules.staff.models.doctor import Doctor
from app.modules.staff.models.doctor_availability import DoctorAvailability

__all__ = [
    "Doctor",
    "DoctorAvailability",
    "doctor_branch",
    "doctor_vertical",
]
```

**Lazy strategy**: como en `clinic`/`catalog`, todas las relaciones en `lazy="raise"`. La M:N `Doctor.branches`/`.verticals`, el `Doctor.user`, y los hijos `availability` se cargan con `selectinload(...)` explícito en el repo, nunca implícitamente.

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (oficiales FastAPI/Pydantic v2 — ver skill `fastapi`, idénticas a [`../clinic/backend.md`](../clinic/backend.md#schemas-pydantic-v2--completos)):
>
> 1. **No usar Ellipsis (`...`)** en `Field(...)`. Campo sin `default=` ya es obligatorio. (El `admin.UserCreate` shipped aún usa `...`; en código nuevo no se replica.)
> 2. **`Annotated`** solo para parámetros HTTP (`Query`, `Path`) en routers.
> 3. **Validators**: `@field_validator` single-field, `@model_validator(mode="after")` cross-field.
> 4. **Mensajes de validator en inglés** (van al detalle 422). El texto user-facing en español vive en el Zod del frontend.

### `schemas/doctor.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.clinic.schemas.branch import BranchOption


class DoctorUserCreate(BaseModel):
    """Nested User payload for DoctorCreate. Mirror of admin.UserCreate minus
    role_ids/permission_ids — the service forces the DOCTOR role. `password` is
    optional: if omitted, the service generates a strong one and returns it once
    (same contract as admin.user.create / UserCreatedResponse)."""

    email: EmailStr
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class DoctorCreate(BaseModel):
    """NESTED create: creates the User (assigning the DOCTOR role) AND the
    Doctor in one transaction. No `user_id` field — the user is born here."""

    user: DoctorUserCreate
    cmp_code: str | None = Field(default=None, max_length=40)
    bio: str | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    slot_duration_min: int = Field(default=30, ge=5, le=240)
    branch_ids: list[str] = Field(default_factory=list)
    vertical_ids: list[str] = Field(default_factory=list)

    @field_validator("branch_ids", "vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("ids must not contain duplicates")
        return v


class DoctorUpdate(BaseModel):
    """Partial update of the professional profile + M:N. NOT updatable:
    `user_id` (immutable 1:1), and the user's identity fields (email/name live
    in the admin User module and are edited there). branch_ids/vertical_ids
    present = full M:N replace; absent = left untouched."""

    cmp_code: str | None = Field(default=None, max_length=40)
    bio: str | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    slot_duration_min: int | None = Field(default=None, ge=5, le=240)
    branch_ids: list[str] | None = None
    vertical_ids: list[str] | None = None
    active: bool | None = None

    @field_validator("branch_ids", "vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("ids must not contain duplicates")
        return v


class DoctorItem(BaseModel):
    """Row of the doctors table. Denormalizes the User's full_name/email so the
    list never needs a join, plus batch branch/vertical counts (same pattern as
    clinic OfficeItem.verticals_count)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    full_name: str   # denormalized from the User
    email: EmailStr  # denormalized from the User
    cmp_code: str | None
    slot_duration_min: int
    active: bool
    branches_count: int
    verticals_count: int
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class DoctorDetail(DoctorItem):
    """Full profile for the detail page. Adds the free-text/media fields, the
    resolved User (audit shape), and the resolved M:N collections (soft-deleted
    branches/verticals filtered out)."""

    bio: str | None
    photo_url: str | None
    signature_url: str | None
    # The 1:1 User resolved to a compact audit shape (id, full_name, email).
    # A richer UserOption can be introduced later if the detail needs phone/docs.
    user: UserAuditInfo
    branches: list[BranchOption]
    verticals: list[VerticalOption]


class DoctorOption(BaseModel):
    """Dropdown shape — used by GET /doctors/active and by scheduling/crm."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    cmp_code: str | None = None


class DoctorCreatedResponse(BaseModel):
    """Returned by POST /doctors — `generated_password` is set when the caller
    didn't supply one and the service generated it (same contract as
    admin.UserCreatedResponse)."""

    success: bool = True
    data: DoctorDetail
    generated_password: str | None = None
```

> **`full_name` / `email` denormalizados**: `Doctor` no tiene esas columnas — viven en `admin.User`. `DoctorItem`/`DoctorOption` no usan `from_attributes` para poblarlos directamente del ORM (no hay atributo `doctor.full_name`); el service los pasa explícitamente (`full_name=doctor.user.full_name`), igual que `clinic.OfficeItem.branch_name`. Por eso el `_to_item` los recibe como kwargs.

> **`from_attributes` necesita el import de `field_validator`**: agregar `field_validator` al import de `pydantic` arriba (`from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator`).

### `schemas/doctor_availability.py`

```python
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class DoctorAvailabilityCreate(BaseModel):
    """One concrete block. Used standalone in bulk create and as the editable
    shape. `closes_at > opens_at` mirrors the DB CHECK."""

    branch_id: str = Field(min_length=1)
    office_id: str = Field(min_length=1)
    date: date_type
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def _closes_after_opens(self) -> DoctorAvailabilityCreate:
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be later than opens_at")
        return self


class DoctorAvailabilityBulkCreate(BaseModel):
    """Body of POST /doctors/{id}/availability — bulk insert ("fill several at
    once"). The service validates the invariants for the whole incoming set AND
    against the doctor's existing blocks on those dates."""

    blocks: list[DoctorAvailabilityCreate] = Field(default_factory=list)


class DoctorAvailabilityUpdate(BaseModel):
    """Edit ONE block (move / resize). All fields optional; cross-field check
    only runs when both times are present after merging with the stored row —
    the service re-validates the merged block (see availability service)."""

    branch_id: str | None = Field(default=None, min_length=1)
    office_id: str | None = Field(default=None, min_length=1)
    date: date_type | None = None
    opens_at: time | None = None
    closes_at: time | None = None


class DoctorAvailabilityItem(BaseModel):
    """One block in a GET response. Denormalizes branch_name/office_code/
    office_name for direct render in the calendar grid (no join in the front)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    doctor_id: str
    branch_id: str
    branch_name: str   # denormalized
    office_id: str
    office_code: str   # denormalized
    office_name: str   # denormalized
    date: date_type
    opens_at: time
    closes_at: time
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
```

> **Por qué `DoctorAvailability` SÍ tiene `Update` por bloque** (a diferencia de `clinic.OfficeOperatingHours`, que es bulk-replace de agregado): un bloque de disponibilidad es una unidad concreta y editable (mover/redimensionar en el calendario), no parte de un patrón semanal atómico. El alta es masiva (`POST` bulk, "pintar varios días"), pero la edición/borrado son **por bloque** (`PUT`/`DELETE` con `ownership`), análogo al CRUD por instancia de `clinic.OfficeClosure` (que tampoco tiene `Update` — pero aquí sí lo necesitamos porque arrastrar un bloque en la grilla es una edición natural, no un borrar+recrear).

## Repositories

`ALLOWED_FIELDS` es el whitelist de columnas filtrable/ordenable desde el frontend (ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md#queryrequest-y-baserepositoryget_paginated)).

```python
# repositories/doctor.py
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.catalog.models.vertical import Vertical
from app.modules.clinic.models.branch import Branch
from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.modules.staff.models.doctor import Doctor
from app.shared.base_repository import BaseRepository


class DoctorRepository(BaseRepository[Doctor]):
    # full_name/email are NOT columns of `doctor` (they live in admin.User), so
    # they are NOT filterable/sortable here. The list orders by created_on by
    # default; client-side filtering by name is done on the denormalized rows.
    ALLOWED_FIELDS: set[str] = {
        "cmp_code", "slot_duration_min", "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Doctor)

    async def get_by_user_id(self, db: AsyncSession, user_id: str) -> Doctor | None:
        """Resolve the Doctor profile of a given user — powers the /me endpoints
        (CurrentAuth.user.id → Doctor) and the one-profile-per-user guard."""
        result = await db.execute(
            select(Doctor).where(Doctor.user_id == user_id, Doctor.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, doctor_id: str) -> Doctor | None:
        # Eager-load the 1:1 User and the M:N branches/verticals, filtering out
        # soft-deleted branches/verticals via `with_loader_criteria` so the M:N
        # load respects the other modules' soft-delete WITHOUT coupling staff to
        # their delete guards (the association rows may still exist).
        return await self.get_by_id(
            db,
            doctor_id,
            load=(
                selectinload(Doctor.user),
                selectinload(Doctor.branches),
                selectinload(Doctor.verticals),
                with_loader_criteria(
                    Branch, Branch.deleted_at.is_(None), include_aliases=True
                ),
                with_loader_criteria(
                    Vertical, Vertical.deleted_at.is_(None), include_aliases=True
                ),
            ),
        )

    async def list_active(
        self,
        db: AsyncSession,
        branch_id: str | None = None,
        vertical_id: str | None = None,
    ) -> list[Doctor]:
        # Eager-load the User so DoctorOption.full_name resolves without N+1.
        # branch_id / vertical_id filter via EXISTS joins on the M:N tables (the
        # branch/vertical must be alive too).
        stmt = (
            select(Doctor)
            .where(Doctor.active.is_(True), Doctor.deleted_at.is_(None))
            .options(selectinload(Doctor.user))
            .order_by(Doctor.created_on.desc())
        )
        if branch_id is not None:
            stmt = stmt.where(
                select(doctor_branch.c.doctor_id)
                .join(Branch, Branch.id == doctor_branch.c.branch_id)
                .where(
                    doctor_branch.c.doctor_id == Doctor.id,
                    doctor_branch.c.branch_id == branch_id,
                    Branch.deleted_at.is_(None),
                )
                .exists()
            )
        if vertical_id is not None:
            stmt = stmt.where(
                select(doctor_vertical.c.doctor_id)
                .join(Vertical, Vertical.id == doctor_vertical.c.vertical_id)
                .where(
                    doctor_vertical.c.doctor_id == Doctor.id,
                    doctor_vertical.c.vertical_id == vertical_id,
                    Vertical.deleted_at.is_(None),
                )
                .exists()
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_branches_map(
        self, db: AsyncSession, doctor_ids: list[str]
    ) -> dict[str, int]:
        """Batch count of attached, non-deleted branches per doctor — one query,
        no N+1. Powers DoctorItem.branches_count."""
        if not doctor_ids:
            return {}
        result = await db.execute(
            select(doctor_branch.c.doctor_id, func.count(doctor_branch.c.branch_id))
            .join(Branch, Branch.id == doctor_branch.c.branch_id)
            .where(
                doctor_branch.c.doctor_id.in_(doctor_ids),
                Branch.deleted_at.is_(None),
            )
            .group_by(doctor_branch.c.doctor_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_verticals_map(
        self, db: AsyncSession, doctor_ids: list[str]
    ) -> dict[str, int]:
        """Batch count of covered, non-deleted verticals per doctor. Powers
        DoctorItem.verticals_count."""
        if not doctor_ids:
            return {}
        result = await db.execute(
            select(doctor_vertical.c.doctor_id, func.count(doctor_vertical.c.vertical_id))
            .join(Vertical, Vertical.id == doctor_vertical.c.vertical_id)
            .where(
                doctor_vertical.c.doctor_id.in_(doctor_ids),
                Vertical.deleted_at.is_(None),
            )
            .group_by(doctor_vertical.c.doctor_id)
        )
        return {row[0]: row[1] for row in result.all()}


doctor_repository = DoctorRepository()
```

> El repo **no** necesita importar `User`: los conteos de `branches`/`verticals` se baten contra las tablas M:N, y el `full_name`/`email` denormalizados los resuelve el service vía `user_repository.get_audit_info_map(...)` (un solo lookup que también cubre los actores de auditoría), no un join en el repo.

```python
# repositories/doctor_availability.py
from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models.doctor_availability import DoctorAvailability
from app.shared.base_repository import BaseRepository


class DoctorAvailabilityRepository(BaseRepository[DoctorAvailability]):
    # Read via list_for_doctor (date-ranged); written per-block. No /list
    # endpoint, so ALLOWED_FIELDS stays empty.
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(DoctorAvailability)

    async def list_for_doctor(
        self,
        db: AsyncSession,
        doctor_id: str,
        date_from: date_type | None = None,
        date_to: date_type | None = None,
    ) -> list[DoctorAvailability]:
        """Blocks of one doctor within an inclusive date range. `from`/`to`
        filter the `date` column (BETWEEN). Ordered by date → opens_at for the
        calendar grid."""
        stmt = (
            select(DoctorAvailability)
            .where(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.deleted_at.is_(None),
            )
            .order_by(
                DoctorAvailability.date.asc(),
                DoctorAvailability.opens_at.asc(),
            )
        )
        if date_from is not None:
            stmt = stmt.where(DoctorAvailability.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(DoctorAvailability.date <= date_to)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_doctor_on_date(
        self, db: AsyncSession, doctor_id: str, on_date: date_type
    ) -> list[DoctorAvailability]:
        """All live blocks of a doctor on a single date — used by the overlap
        invariant (#3) to check the incoming block against existing ones."""
        return await self.list_for_doctor(db, doctor_id, on_date, on_date)


doctor_availability_repository = DoctorAvailabilityRepository()
```

## API contracts

Todos los endpoints usan los envelopes del template (idénticos a [`../clinic/backend.md`](../clinic/backend.md#api-contracts)):
- **Single**: `{ "success": true, "data": <T> }`
- **Paginated**: `{ "success": true, "data": { "items": [...], "total": N, "skip": 0, "limit": 10 } }`
- **Lista cruda** (endpoints `/active`): el body es directamente `[...]` (sin envelope).
- **Error**: `{ "success": false, "detail": "...", "code"?: "...", "errors"?: [...] }`

Prefijo común: `/api/v1/staff/`. Listados paginados con `POST /<recurso>/list` + `QueryRequest`. Convención `PUT` (no `PATCH`); `/active` antes de `/{id}` en el router.

### Doctores (admin)

#### `POST /api/v1/staff/doctors/list`

**Permiso**: `DOCTORS_READ`.

**Request** (`QueryRequest`):
```json
{
  "pagination": { "skip": 0, "limit": 10 },
  "sorting":    { "sort_by": "created_on", "sort_order": "desc" },
  "filters": {
    "filters": [
      { "operator": "AND", "conditions": [
        { "field": "active", "operator": "eq", "value": true }
      ] }
    ]
  }
}
```

> `full_name`/`email` **no** son filtrables aquí (no son columnas de `doctor`); el filtrado por nombre se hace client-side sobre las filas denormalizadas, o se delega al filtro por sede/vertical (deep-link `?branch_id=`/`?vertical_id=` que la página traduce a un `EXISTS` — ver `frontend.md`). `cmp_code`, `slot_duration_min`, `active` sí están en `ALLOWED_FIELDS`.

**Response** (`PaginatedResponse[DoctorItem]`):
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "d1a2...",
        "user_id": "u9f8...",
        "full_name": "Juan Pérez García",
        "email": "jperez@medisage.pe",
        "cmp_code": "CMP-45821",
        "slot_duration_min": 30,
        "active": true,
        "branches_count": 2,
        "verticals_count": 3,
        "created_on": "2026-05-29T14:23:10+00:00",
        "created_by": "00000000-0000-0000-0000-000000000001",
        "created_by_user": { "id": "...", "full_name": "Admin User", "email": "admin@..." },
        "updated_on": "2026-05-29T14:23:10+00:00",
        "updated_by": "...",
        "updated_by_user": { "...": "..." }
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 10
  }
}
```

#### `POST /api/v1/staff/doctors`

**Permiso**: `DOCTORS_CREATE`. Creación **NESTED**: crea el `User` (con role `DOCTOR`) y el `Doctor` en una transacción.

**Request** (`DoctorCreate`):
```json
{
  "user": {
    "email": "jperez@medisage.pe",
    "first_name": "Juan",
    "last_name": "Pérez",
    "second_last_name": "García",
    "document_type": "DNI",
    "document_number": "45821073",
    "phone": "+51 999 888 777"
  },
  "cmp_code": "CMP-45821",
  "bio": "Cirujano dentista con 12 años de experiencia.",
  "photo_url": "https://cdn.medisage.pe/doctors/jperez.jpg",
  "signature_url": null,
  "slot_duration_min": 30,
  "branch_ids": ["b1a2...", "b3c4..."],
  "vertical_ids": ["v8c5...", "v9d6..."]
}
```

`user.password` es opcional: si se omite, el service genera una contraseña fuerte y la devuelve **una sola vez** en `generated_password`.

**Response 201** (`DoctorCreatedResponse` — mismo shape que `UserCreatedResponse`: `{success, data, generated_password}`):
```json
{
  "success": true,
  "data": {
    "id": "d1a2...",
    "user_id": "u9f8...",
    "full_name": "Juan Pérez García",
    "email": "jperez@medisage.pe",
    "cmp_code": "CMP-45821",
    "slot_duration_min": 30,
    "active": true,
    "branches_count": 2,
    "verticals_count": 2,
    "bio": "Cirujano dentista con 12 años de experiencia.",
    "photo_url": "https://cdn.medisage.pe/doctors/jperez.jpg",
    "signature_url": null,
    "user": { "id": "u9f8...", "full_name": "Juan Pérez García", "email": "jperez@medisage.pe" },
    "branches": [
      { "id": "b1a2...", "code": "lima_centro", "name": "Sede Lima Centro", "city": "Lima", "timezone": "America/Lima" },
      { "id": "b3c4...", "code": "trujillo", "name": "Sede Trujillo", "city": "Trujillo", "timezone": "America/Lima" }
    ],
    "verticals": [
      { "id": "v8c5...", "code": "dental", "name": "Dental", "color": "#3B82F6", "icon": "ToothRegular" },
      { "id": "v9d6...", "code": "estetica_facial", "name": "Estética facial", "color": "#FF6B6B", "icon": "Sparkle24Regular" }
    ],
    "created_on": "2026-05-29T14:23:10+00:00",
    "created_by": "...",
    "created_by_user": { "...": "..." },
    "updated_on": "2026-05-29T14:23:10+00:00",
    "updated_by": "...",
    "updated_by_user": { "...": "..." }
  },
  "generated_password": "Xk7$mPq2vL9w"
}
```

**Error 409** (email ya registrado):
```json
{ "success": false, "detail": "El correo 'jperez@medisage.pe' ya está registrado", "code": "EMAIL_TAKEN" }
```

**Error 400** (algún `branch_id` no existe o está soft-deleted):
```json
{ "success": false, "detail": "Sede(s) no encontrada(s): b3c4..." }
```

**Error 400** (algún `vertical_id` no existe o está soft-deleted):
```json
{ "success": false, "detail": "Vertical(es) no encontrada(s): v9d6..." }
```

#### `GET /api/v1/staff/doctors/{id}` → `SingleResponse[DoctorDetail]`

**Permiso**: `DOCTORS_READ`. Incluye `user` (audit shape), `branches` (list[BranchOption]) y `verticals` (list[VerticalOption]) resueltos; branches/verticals soft-deleted excluidos vía `with_loader_criteria` (ver repo `get_full`).

**Error 404**:
```json
{ "success": false, "detail": "Doctor no encontrado", "code": "DOCTOR_NOT_FOUND" }
```

#### `PUT /api/v1/staff/doctors/{id}`

**Permiso**: `DOCTORS_UPDATE`.

**Request** (`DoctorUpdate`): subset; `branch_ids`/`vertical_ids` presentes = **reemplazo total** de la M:N; ausentes = se dejan tal cual.
```json
{
  "cmp_code": "CMP-45821",
  "slot_duration_min": 20,
  "branch_ids": ["b1a2..."],
  "active": true
}
```

`user_id` y la identidad del User (email/nombre/documento) **no** son actualizables aquí — esos campos viven en `admin` y se editan en `/api/v1/admin/users/{id}`. `DoctorUpdate` no los declara; el server descarta cualquier slot inesperado (belt-and-suspenders).

**Response** `SingleResponse[DoctorDetail]` (mismo shape que el GET).

**Error 400** si algún `branch_id`/`vertical_id` no existe o está soft-deleted (igual que en create).

#### `DELETE /api/v1/staff/doctors/{id}` → soft-delete

**Permiso**: `DOCTORS_DELETE`. **Response 204** sin body. **NO** toca el `User` (ADR-002): para bloquear el acceso del doctor a la plataforma hay que poner `user.active = false` desde `admin`. Las filas `doctor_branch`/`doctor_vertical` y los bloques de `doctor_availability` quedan colgados pero filtrados por el `deleted_at` del doctor en cualquier lectura.

**Error 404**:
```json
{ "success": false, "detail": "Doctor no encontrado", "code": "DOCTOR_NOT_FOUND" }
```

> **Sin guard 409 de children**: la disponibilidad de un doctor son value aggregates internos (no entidades de otros módulos), así que borrar un doctor con bloques es válido — los bloques se filtran por el `deleted_at` del doctor. (Las citas futuras en `scheduling` que apunten a un doctor borrado las maneja `scheduling`, no `staff`.)

#### `GET /api/v1/staff/doctors/active?branch_id=&vertical_id=`

**Permiso**: `DOCTORS_READ`. Ambos query params opcionales. `branch_id` filtra doctores asignados a esa sede; `vertical_id` filtra doctores que cubren esa vertical (EXISTS join sobre `doctor_branch`/`doctor_vertical`, excluyendo branches/verticals soft-deleted). Devuelve **lista cruda** `list[DoctorOption]`:
```json
[
  { "id": "d1a2...", "full_name": "Juan Pérez García", "cmp_code": "CMP-45821" },
  { "id": "d5e6...", "full_name": "María López Ríos", "cmp_code": "CMP-90412" }
]
```

### Disponibilidad de un doctor (admin)

Anidada bajo `/doctors/{doctor_id}/availability/...`. El service valida que el doctor exista (404 `DOCTOR_NOT_FOUND`) y los invariantes 1-3 (códigos abajo).

#### `GET /api/v1/staff/doctors/{id}/availability?from=&to=`

**Permiso**: `DOCTOR_AVAILABILITY_READ`. `from`/`to` son `date` ISO (`YYYY-MM-DD`); filtran `date` BETWEEN `from`..`to` (inclusive). Sin filtros devuelve todos los bloques no borrados del doctor (la UI siempre manda el rango de la semana visible).

**Response** `SingleResponse[list[DoctorAvailabilityItem]]`:
```json
{
  "success": true,
  "data": [
    {
      "id": "a1...",
      "doctor_id": "d1a2...",
      "branch_id": "b1a2...",
      "branch_name": "Sede Lima Centro",
      "office_id": "o9f8...",
      "office_code": "C-03",
      "office_name": "Consultorio 3 — Dental",
      "date": "2026-06-01",
      "opens_at": "08:00:00",
      "closes_at": "13:00:00",
      "active": true,
      "created_on": "2026-05-29T14:23:10+00:00",
      "created_by": "...",
      "created_by_user": { "...": "..." },
      "updated_on": "2026-05-29T14:23:10+00:00",
      "updated_by": "...",
      "updated_by_user": { "...": "..." }
    }
  ]
}
```

**Error 404** si el doctor no existe:
```json
{ "success": false, "detail": "Doctor no encontrado", "code": "DOCTOR_NOT_FOUND" }
```

#### `POST /api/v1/staff/doctors/{id}/availability`

**Permiso**: `DOCTOR_AVAILABILITY_WRITE`. **Alta masiva**: el body es `DoctorAvailabilityBulkCreate` con una lista de bloques (al "pintar" varios días en la grilla se manda uno por día).

**Request** (`DoctorAvailabilityBulkCreate`):
```json
{
  "blocks": [
    { "branch_id": "b1a2...", "office_id": "o9f8...", "date": "2026-06-01", "opens_at": "08:00:00", "closes_at": "13:00:00" },
    { "branch_id": "b1a2...", "office_id": "o9f8...", "date": "2026-06-02", "opens_at": "08:00:00", "closes_at": "13:00:00" },
    { "branch_id": "b1a2...", "office_id": "o9f8...", "date": "2026-06-03", "opens_at": "08:00:00", "closes_at": "13:00:00" }
  ]
}
```

**Response 201** `SingleResponse[list[DoctorAvailabilityItem]]` — los bloques creados (mismo shape que el GET).

**Error 400** — invariante 1 (`office_id` no pertenece a `branch_id`):
```json
{ "success": false, "detail": "El consultorio no pertenece a la sede indicada", "code": "OFFICE_NOT_IN_BRANCH" }
```

**Error 400** — invariante 2 (el doctor no está asignado a `branch_id`):
```json
{ "success": false, "detail": "El doctor no está asignado a esta sede", "code": "DOCTOR_NOT_IN_BRANCH" }
```

**Error 400** — invariante 3 (solapamiento con un bloque existente o entre bloques del propio body):
```json
{ "success": false, "detail": "El bloque se solapa con otra disponibilidad del doctor el 2026-06-01", "code": "AVAILABILITY_OVERLAP" }
```

**Error 422** — `closes_at <= opens_at` (validator Pydantic, mensaje en inglés):
```json
{
  "success": false,
  "detail": "Validation failed",
  "errors": [{ "loc": ["body", "blocks", 0], "msg": "closes_at must be later than opens_at", "type": "value_error" }]
}
```

**Error 404** si el doctor no existe → `DOCTOR_NOT_FOUND`.

#### `PUT /api/v1/staff/doctors/{id}/availability/{block_id}`

**Permiso**: `DOCTOR_AVAILABILITY_WRITE`. Edita un bloque (mover/redimensionar). El service mergea el payload sobre el bloque guardado, re-valida `closes_at > opens_at` y los invariantes 1-3 (excluyendo el propio bloque del chequeo de solape).

**Request** (`DoctorAvailabilityUpdate`):
```json
{ "opens_at": "09:00:00", "closes_at": "14:00:00" }
```

**Response** `SingleResponse[DoctorAvailabilityItem]`.

**Error 404** si el bloque no existe o no pertenece a ese doctor (ownership):
```json
{ "success": false, "detail": "Disponibilidad no encontrada", "code": "AVAILABILITY_NOT_FOUND" }
```

Mismos `400 OFFICE_NOT_IN_BRANCH` / `DOCTOR_NOT_IN_BRANCH` / `AVAILABILITY_OVERLAP` y `422 closes_at` que el POST.

#### `DELETE /api/v1/staff/doctors/{id}/availability/{block_id}` → soft-delete

**Permiso**: `DOCTOR_AVAILABILITY_WRITE`. **Response 204**.

**Error 404** si el bloque no existe o no pertenece a ese doctor → `AVAILABILITY_NOT_FOUND`.

### Self-service `/me` (el doctor logueado) — fase F3

El service resuelve el `doctor` desde `CurrentAuth.user.id` (`doctor_repository.get_by_user_id`). Si el user no tiene perfil → `403 ForbiddenException(code="NOT_A_DOCTOR")`. Esto separa "editar mi propia agenda" (role `DOCTOR`) de "editar la agenda de cualquier doctor" (role `ADMIN`). El **resto del contrato (shapes, invariantes, errores) es idéntico** a los endpoints admin equivalentes — solo cambia el permiso y la resolución implícita del doctor.

| Método | Ruta | Permiso | Shape |
|---|---|---|---|
| GET | `/me/doctor` | `MY_DOCTOR_PROFILE_READ` | `SingleResponse[DoctorDetail]` |
| PUT | `/me/doctor` | `MY_DOCTOR_PROFILE_WRITE` | `SingleResponse[DoctorDetail]` |
| GET | `/me/availability?from=&to=` | `MY_AVAILABILITY_READ` | `SingleResponse[list[DoctorAvailabilityItem]]` |
| POST | `/me/availability` | `MY_AVAILABILITY_WRITE` | `SingleResponse[list[DoctorAvailabilityItem]]` (201) |
| PUT | `/me/availability/{block_id}` | `MY_AVAILABILITY_WRITE` | `SingleResponse[DoctorAvailabilityItem]` |
| DELETE | `/me/availability/{block_id}` | `MY_AVAILABILITY_WRITE` | 204 |

**`PUT /me/doctor`** acepta solo `cmp_code`, `bio`, `photo_url`, `signature_url`, `slot_duration_min` (un `DoctorSelfUpdate` reducido de `DoctorUpdate`). **NO** acepta `branch_ids`/`vertical_ids` ni `active` — asignar sedes/verticales y habilitar/deshabilitar es decisión del admin. Si el front manda esos campos, el service los descarta.

**Error 403** (user logueado sin perfil de doctor) en cualquier `/me/*`:
```json
{ "success": false, "detail": "Tu usuario no tiene un perfil de doctor", "code": "NOT_A_DOCTOR" }
```

## Lógica importante (decisiones que el código no expresa solo)

### Creación NESTED de Doctor (User + role DOCTOR + Doctor en una transacción)

`POST /doctors` espeja `admin.user.create` (genera password si falta y la devuelve una vez) pero además fuerza el role `DOCTOR` y crea el `Doctor` en la misma transacción del request:

```python
# services/doctor.py — create
async def create(
    db: AsyncSession, payload: DoctorCreate, *, actor_id: str
) -> DoctorCreatedResponse:
    # 1) Email uniqueness (same guard as admin.user.create) — 409 EMAIL_TAKEN.
    existing = await user_repository.get_by_email(db, payload.user.email)
    if existing is not None:
        raise AlreadyExistsException(
            f"El correo '{payload.user.email}' ya está registrado", code="EMAIL_TAKEN"
        )

    # 2) Resolve M:N targets up front so a bad id fails before we create the User
    #    (the whole thing is one transaction, but failing early keeps it clean).
    branches = await _resolve_branches(db, payload.branch_ids)
    verticals = await _resolve_verticals(db, payload.vertical_ids)

    # 3) The DOCTOR role (seeded). The new user gets exactly this role. The
    #    lookup + guard live in a named helper `_get_doctor_role`.
    doctor_role = await _get_doctor_role(db)

    # 4) Create the User (assigning the DOCTOR role). Generate a password if the
    #    caller didn't supply one — returned once in `generated_password`.
    plain = payload.user.password or generate_password()
    now = utc_now()
    user = User(
        id=generate_uuid(),
        email=payload.user.email,
        password_hash=hash_password(plain),
        first_name=payload.user.first_name,
        last_name=payload.user.last_name,
        second_last_name=payload.user.second_last_name,
        document_type=payload.user.document_type,
        document_number=payload.user.document_number,
        phone=payload.user.phone,
        active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
        roles=[doctor_role],
    )
    db.add(user)
    await db.flush()  # materialize user.id for the FK below

    # 5) Create the Doctor (1:1).
    doctor = Doctor(
        id=generate_uuid(),
        user_id=user.id,
        cmp_code=payload.cmp_code,
        bio=payload.bio,
        photo_url=payload.photo_url,
        signature_url=payload.signature_url,
        slot_duration_min=payload.slot_duration_min,
        active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
        branches=branches,
        verticals=verticals,
    )
    db.add(doctor)
    await db.flush()

    # 6) Reload with user + branches + verticals eager-loaded (lazy="raise").
    created = await doctor_repository.get_full(db, doctor.id)
    audit_users = await user_repository.get_audit_info_map(
        db, {created.created_by, created.updated_by}
    )
    return DoctorCreatedResponse(
        data=_to_detail(created, audit_users),
        generated_password=plain if payload.user.password is None else None,
    )
```

**Atomicidad**: todo corre en la transacción del request (`get_db` hace `commit` al final, `rollback` si algo lanza). Si la creación del `Doctor` falla (ej. una constraint), el `User` recién creado se revierte — nunca queda un User huérfano sin perfil. No hay `commit` intermedio (`flush` solo materializa el `id` para el FK).

> **Consistencia con ADR-002**: si más adelante `admin` permite asignar el role `DOCTOR` a un user existente sin perfil, ese path debe forzar la creación del `Doctor` o quitar el role. Hoy `staff.create` es el único camino que nace doctores, y siempre crea ambos.

### Resolución de las M:N (branches / verticals) en create / update

Mismo patrón que `clinic._resolve_verticals` / `admin._resolve_roles`:

```python
# services/doctor.py
async def _resolve_branches(db: AsyncSession, branch_ids: list[str]) -> list[Branch]:
    if not branch_ids:
        return []
    branches = await branch_repository.get_by_ids(db, branch_ids)  # filters deleted_at
    if len(branches) != len(set(branch_ids)):
        found = {b.id for b in branches}
        missing = sorted(set(branch_ids) - found)
        raise BadRequestException(f"Sede(s) no encontrada(s): {', '.join(missing)}")
    return branches


async def _resolve_verticals(db: AsyncSession, vertical_ids: list[str]) -> list[Vertical]:
    if not vertical_ids:
        return []
    verticals = await vertical_repository.get_by_ids(db, vertical_ids)  # filters deleted_at
    if len(verticals) != len(set(vertical_ids)):
        found = {v.id for v in verticals}
        missing = sorted(set(vertical_ids) - found)
        raise BadRequestException(f"Vertical(es) no encontrada(s): {', '.join(missing)}")
    return verticals


async def _get_doctor_role(db: AsyncSession) -> Role:
    # Invariante de seed: el rol DOCTOR siempre existe (F0). Si falta, es un error
    # de configuración — fallar claro con un `code` en vez de crear un user sin rol.
    role = await role_repository.get_by_name(db, DOCTOR_ROLE_NAME)
    if role is None:
        raise BadRequestException(
            "El rol DOCTOR no está configurado en el sistema", code="DOCTOR_ROLE_MISSING"
        )
    return role
```

En `update`: solo si `branch_ids`/`vertical_ids` vienen en el payload (`exclude_unset`) se hace `doctor.branches = await _resolve_branches(...)` / `doctor.verticals = await _resolve_verticals(...)` (reemplazo total). Tras crear/actualizar, **recargar con `get_full`** para rehidratar `user`/`branches`/`verticals` (las relaciones `lazy="raise"` quedan sin cargar tras el `flush`/`refresh` — mismo patrón reload-via-get_full de `clinic`/`catalog`).

> **`branch_repository.get_by_ids`**: helper análogo a `vertical_repository.get_by_ids`/`role_repository.get_by_ids`. Si `clinic.BranchRepository` aún no lo expone, agregarlo en F1 (`select(Branch).where(Branch.id.in_(ids), Branch.deleted_at.is_(None))`) — cambio aditivo y desacoplado.

### Hidratar `full_name`/`email`/`branches_count`/`verticals_count` (denormalizado, sin N+1)

`DoctorItem` lleva el `full_name`/`email` del User y los counts denormalizados. En el listado, **un solo lookup de users** (que cubre tanto el `full_name`/`email` de cada doctor como los actores de auditoría `created_by`/`updated_by`) más dos conteos batch — sin N+1, igual que `clinic.office.list_paginated`:

```python
# services/doctor.py — list_paginated
async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[DoctorItem]:
    items, total = await doctor_repository.get_paginated(db, query_request)
    doctor_ids = [d.id for d in items]
    # Un solo lookup de users cubre tanto a los doctores (full_name/email) como a
    # los actores de auditoría; dos conteos batch para los M:N. Sin N+1.
    user_ids = {d.user_id for d in items} | _collect_actor_ids(items)
    users = await user_repository.get_audit_info_map(db, user_ids)
    bcounts = await doctor_repository.count_branches_map(db, doctor_ids)
    vcounts = await doctor_repository.count_verticals_map(db, doctor_ids)
    rows: list[DoctorItem] = []
    for d in items:
        du = users.get(d.user_id)
        rows.append(
            _to_item(
                d, users,
                full_name=du.full_name if du else "",
                email=du.email if du else "desconocido@desconocido.local",
                branches_count=bcounts.get(d.id, 0),
                verticals_count=vcounts.get(d.id, 0),
            )
        )
    return PaginatedResponse(
        data=PaginatedData(
            items=rows,
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )
```

`_to_item` recibe el `full_name`/`email` ya resueltos del User; si por algún motivo el user no está (no debería pasar — el FK es NOT NULL), cae a un string vacío / placeholder. Para `DoctorDetail` (`get_by_id`, post-create, post-update), `get_full` ya hizo `selectinload(Doctor.user/branches/verticals)` con el filtro de soft-delete, así que `_to_detail` lee `doctor.user`, `doctor.branches`, `doctor.verticals` sin más queries.

### Invariantes de `DoctorAvailability` (validados en service, con código de error)

Los tres invariantes son cross-tabla, así que viven en el service (no como CHECK). Se validan en `POST` bulk (para cada bloque entrante, y los bloques del body entre sí) y en `PUT` (para el bloque mergeado):

```python
# services/doctor_availability.py — núcleo de la validación de un bloque
async def _validate_block(
    db: AsyncSession,
    doctor: Doctor,
    branch_id: str,
    office_id: str,
    on_date: date_type,
    opens_at: time,
    closes_at: time,
    *,
    existing_same_date: list[DoctorAvailability],   # ya cargados (incl. los del body)
    exclude_block_id: str | None = None,            # el propio bloque en un PUT
) -> None:
    # Invariante 1: el office pertenece al branch.
    office = await office_repository.get_by_id(db, office_id)
    if office is None or office.branch_id != branch_id:
        raise BadRequestException(
            "El consultorio no pertenece a la sede indicada", code="OFFICE_NOT_IN_BRANCH"
        )
    # Invariante 2: el doctor está asignado a ese branch (doctor_branch).
    if branch_id not in {b.id for b in doctor.branches}:
        raise BadRequestException(
            "El doctor no está asignado a esta sede", code="DOCTOR_NOT_IN_BRANCH"
        )
    # Invariante 3: no-solape con otros bloques del MISMO doctor en la MISMA date.
    #   Adyacentes OK ([08-13) y [13-20) no se solapan). Half-open [opens, closes).
    for other in existing_same_date:
        if exclude_block_id is not None and other.id == exclude_block_id:
            continue
        if opens_at < other.closes_at and other.opens_at < closes_at:
            raise BadRequestException(
                f"El bloque se solapa con otra disponibilidad del doctor el {on_date.isoformat()}",
                code="AVAILABILITY_OVERLAP",
            )
```

> **Invariante 4 (suave, no se bloquea)**: idealmente el bloque cabe dentro del `OfficeOperatingHours` del office para el weekday de `date`. **NO se valida como hard-block en `staff`** — `scheduling` intersecta el bloque del doctor con el horario del office, así que la porción fuera de horario simplemente no genera slots. Se documenta para que el implementador no agregue un guard de más. (La UI puede mostrar el `OfficeOperatingHours` como banda guía — ver `ui.md`.)

**Bulk create** — ordenar para validar también entre los bloques del propio body:

```python
# services/doctor_availability.py — bulk_create (esqueleto)
async def bulk_create(
    db: AsyncSession, doctor_id: str, payload: DoctorAvailabilityBulkCreate, *, actor_id: str
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    doctor = await doctor_repository.get_full(db, doctor_id)   # carga branches para inv. 2
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")

    now = utc_now()
    created: list[DoctorAvailability] = []
    # Per-date accumulator: existing live blocks + the ones already added in THIS
    # body, so two body blocks on the same date are checked against each other.
    by_date: dict[date_type, list[DoctorAvailability]] = {}
    for block in payload.blocks:
        if block.date not in by_date:
            by_date[block.date] = await doctor_availability_repository.list_for_doctor_on_date(
                db, doctor_id, block.date
            )
        await _validate_block(
            db, doctor, block.branch_id, block.office_id, block.date,
            block.opens_at, block.closes_at,
            existing_same_date=by_date[block.date],
        )
        row = DoctorAvailability(
            id=generate_uuid(), doctor_id=doctor_id,
            branch_id=block.branch_id, office_id=block.office_id, date=block.date,
            opens_at=block.opens_at, closes_at=block.closes_at, active=True,
            created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
        )
        db.add(row)
        by_date[block.date].append(row)   # subsequent body blocks see this one
        created.append(row)
    await db.flush()
    return SingleResponse(data=await _to_items(db, created))
```

**`PUT` de un bloque (mover/redimensionar)** con ownership:

```python
# services/doctor_availability.py — update_block
async def update_block(
    db: AsyncSession, doctor_id: str, block_id: str, payload: DoctorAvailabilityUpdate,
    *, actor_id: str,
) -> SingleResponse[DoctorAvailabilityItem]:
    doctor = await doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    block = await doctor_availability_repository.get_by_id(db, block_id)
    # Ownership: the block must exist AND belong to this doctor.
    if block is None or block.doctor_id != doctor_id:
        raise NotFoundException("Disponibilidad no encontrada", code="AVAILABILITY_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    merged_branch = changes.get("branch_id", block.branch_id)
    merged_office = changes.get("office_id", block.office_id)
    merged_date = changes.get("date", block.date)
    merged_opens = changes.get("opens_at", block.opens_at)
    merged_closes = changes.get("closes_at", block.closes_at)
    if merged_closes <= merged_opens:
        raise BadRequestException("closes_at must be later than opens_at")

    same_date = await doctor_availability_repository.list_for_doctor_on_date(
        db, doctor_id, merged_date
    )
    await _validate_block(
        db, doctor, merged_branch, merged_office, merged_date,
        merged_opens, merged_closes,
        existing_same_date=same_date, exclude_block_id=block_id,
    )
    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()
    await doctor_availability_repository.update(db, block, changes)
    return SingleResponse(data=(await _to_items(db, [block]))[0])
```

`DELETE` valida la misma ownership (404 `AVAILABILITY_NOT_FOUND` si no existe o es de otro doctor) y hace `soft_delete`.

> **`_to_items` denormaliza branch_name / office_code / office_name**: batch lookups de `branch.name` y `(office.code, office.name)` por los `branch_id`/`office_id` de los bloques (mismo patrón que `branch_name_map`), para evitar N+1 al construir `DoctorAvailabilityItem`. No hay relación ORM cargada en los bloques (`DoctorAvailability` solo tiene `doctor` como rel), así que los nombres se resuelven con queries batch en el service.

### Self-service `/me`: resolver el doctor desde `CurrentAuth`

```python
# services/me.py
async def _require_my_doctor(db: AsyncSession, auth: AuthContext) -> Doctor:
    doctor = await doctor_repository.get_by_user_id(db, auth.user.id)
    if doctor is None:
        raise ForbiddenException(
            "Tu usuario no tiene un perfil de doctor", code="NOT_A_DOCTOR"
        )
    return doctor
```

Cada función `/me/*` empieza resolviendo el doctor y luego delega en la **misma lógica** que el path admin (reusa `doctor_availability` service pasándole el `doctor.id` resuelto). El permiso (`MY_*` en vez de `DOCTOR_*`/`DOCTORS_*`) lo aplica el router; la diferencia funcional es solo de quién puede tocar qué. `PUT /me/doctor` usa un `DoctorSelfUpdate` reducido (solo `cmp_code`/`bio`/`photo_url`/`signature_url`/`slot_duration_min`) para que el doctor no pueda reasignarse sedes/verticales ni activarse.

### Inmutabilidad de `user_id` y de la identidad del User

- `Doctor.user_id` es **inmutable** (1:1 estable; `DoctorUpdate` no lo declara, el server descarta cualquier slot inesperado).
- Email/nombre/documento/teléfono del User **no** se editan desde `staff` — viven en `admin` y se editan en `PUT /api/v1/admin/users/{id}`. `staff` solo posee los campos profesionales (`cmp_code`, `bio`, `photo_url`, `signature_url`, `slot_duration_min`) + las M:N.

### `BaseRepository` filtra `deleted_at IS NULL` automáticamente

Igual que `clinic`/`catalog`: en `get_by_id`/`get_paginated` **no** repetir el filtro. Para queries custom (`get_by_user_id`, `list_active`, `list_for_doctor`, los counts/maps), sí hay que agregarlo explícitamente como en los ejemplos.

### Audit columns con `created_by` / `updated_by`

Cada service que persiste recibe `actor_id` explícito desde el router (patrón shipped: `actor: CurrentAuth` aparte del `dependencies=[Depends(RequirePermission(...))]`). En la creación NESTED, **tanto el `User` como el `Doctor`** llevan `created_by = actor_id` (el admin que los creó), no se atribuyen a sí mismos.

## Routers — ejemplos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]` en el decorator; `actor: CurrentAuth` aparte cuando se necesita el id para audit; `/active` antes de `/{id}` para que no lo capture la ruta dinámica.

```python
# routers/doctor.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.staff.schemas.doctor import (
    DoctorCreate,
    DoctorCreatedResponse,
    DoctorDetail,
    DoctorItem,
    DoctorOption,
    DoctorUpdate,
)
from app.modules.staff.services import doctor as doctor_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/doctors", tags=["staff · doctors"])

DoctorIdPath = Annotated[str, Path(min_length=1, description="Doctor UUID")]


@router.get(
    "/active",
    response_model=list[DoctorOption],
    dependencies=[Depends(RequirePermission("DOCTORS_READ"))],
)
async def list_active_doctors(
    db: DBSession,
    branch_id: str | None = None,
    vertical_id: str | None = None,
) -> list[DoctorOption]:
    return await doctor_service.list_active(db, branch_id=branch_id, vertical_id=vertical_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[DoctorItem],
    dependencies=[Depends(RequirePermission("DOCTORS_READ"))],
)
async def list_doctors(query: QueryRequest, db: DBSession) -> PaginatedResponse[DoctorItem]:
    return await doctor_service.list_paginated(db, query)


@router.post(
    "",
    response_model=DoctorCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("DOCTORS_CREATE"))],
)
async def create_doctor(
    payload: DoctorCreate, db: DBSession, actor: CurrentAuth
) -> DoctorCreatedResponse:
    return await doctor_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{doctor_id}",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("DOCTORS_READ"))],
)
async def get_doctor(doctor_id: DoctorIdPath, db: DBSession) -> SingleResponse[DoctorDetail]:
    return await doctor_service.get_by_id(db, doctor_id)


@router.put(
    "/{doctor_id}",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("DOCTORS_UPDATE"))],
)
async def update_doctor(
    doctor_id: DoctorIdPath, payload: DoctorUpdate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[DoctorDetail]:
    return await doctor_service.update(db, doctor_id, payload, actor_id=actor.id)


@router.delete(
    "/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("DOCTORS_DELETE"))],
)
async def delete_doctor(doctor_id: DoctorIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await doctor_service.soft_delete(db, doctor_id, actor_id=actor.id)
```

El router de disponibilidad cuelga de `/doctors/{doctor_id}/availability/...`:

```python
# routers/doctor_availability.py
from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.staff.schemas.doctor_availability import (
    DoctorAvailabilityBulkCreate,
    DoctorAvailabilityItem,
    DoctorAvailabilityUpdate,
)
from app.modules.staff.services import doctor_availability as availability_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/doctors", tags=["staff · availability"])

DoctorIdPath = Annotated[str, Path(min_length=1, description="Doctor UUID")]
BlockIdPath = Annotated[str, Path(min_length=1, description="Availability block UUID")]


@router.get(
    "/{doctor_id}/availability",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_READ"))],
)
async def list_availability(
    doctor_id: DoctorIdPath,
    db: DBSession,
    from_: Annotated[date_type | None, Query(alias="from")] = None,
    to: Annotated[date_type | None, Query()] = None,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await availability_service.list_for_doctor(db, doctor_id, from_, to)


@router.post(
    "/{doctor_id}/availability",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_WRITE"))],
)
async def create_availability(
    doctor_id: DoctorIdPath,
    payload: DoctorAvailabilityBulkCreate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await availability_service.bulk_create(db, doctor_id, payload, actor_id=actor.id)


@router.put(
    "/{doctor_id}/availability/{block_id}",
    response_model=SingleResponse[DoctorAvailabilityItem],
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_WRITE"))],
)
async def update_availability(
    doctor_id: DoctorIdPath,
    block_id: BlockIdPath,
    payload: DoctorAvailabilityUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[DoctorAvailabilityItem]:
    return await availability_service.update_block(
        db, doctor_id, block_id, payload, actor_id=actor.id
    )


@router.delete(
    "/{doctor_id}/availability/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_WRITE"))],
)
async def delete_availability(
    doctor_id: DoctorIdPath,
    block_id: BlockIdPath,
    db: DBSession,
    actor: CurrentAuth,
) -> None:
    await availability_service.delete_block(db, doctor_id, block_id, actor_id=actor.id)
```

El router `/me` resuelve el doctor desde `CurrentAuth` y reusa los services:

```python
# routers/me.py
router = APIRouter(prefix="/me", tags=["staff · me"])


@router.get(
    "/doctor",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("MY_DOCTOR_PROFILE_READ"))],
)
async def get_my_doctor(db: DBSession, auth: CurrentAuth) -> SingleResponse[DoctorDetail]:
    return await me_service.get_my_doctor(db, auth)


@router.put(
    "/doctor",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("MY_DOCTOR_PROFILE_WRITE"))],
)
async def update_my_doctor(
    payload: DoctorSelfUpdate, db: DBSession, auth: CurrentAuth
) -> SingleResponse[DoctorDetail]:
    return await me_service.update_my_doctor(db, auth, payload)


@router.get(
    "/availability",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    dependencies=[Depends(RequirePermission("MY_AVAILABILITY_READ"))],
)
async def list_my_availability(
    db: DBSession,
    auth: CurrentAuth,
    from_: Annotated[date_type | None, Query(alias="from")] = None,
    to: Annotated[date_type | None, Query()] = None,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await me_service.list_my_availability(db, auth, from_, to)

# POST/PUT/DELETE /me/availability/* análogos: resuelven el doctor con
# _require_my_doctor y delegan en availability_service con doctor.id.
```

> `from` es palabra reservada en Python; el parámetro se declara `from_` con `Query(alias="from")` para mantener `?from=` en la URL (igual que `clinic.office_closure`).

## Migrations

Migraciones **manuales y numeradas** (convención medisage). La última de `clinic` es `0008_clinic_office_closure`; `staff` encadena desde ahí. Una migración por entidad, alineada a las fases. **Revision id ≤ 32 chars** (límite `alembic_version.varchar(32)`). Las `CheckConstraint` se declaran **tanto en `__table_args__` como en el SQL** de la migración.

### `0009_staff_doctor.py` (F1 — doctor + doctor_branch / doctor_vertical M:N)

```sql
CREATE TABLE doctor (
    id                VARCHAR(36) PRIMARY KEY,
    user_id           VARCHAR(36) NOT NULL UNIQUE REFERENCES "user"(id),  -- RESTRICT, 1:1
    cmp_code          VARCHAR(40),
    bio               TEXT,
    photo_url         VARCHAR(500),
    signature_url     VARCHAR(500),
    slot_duration_min INTEGER NOT NULL DEFAULT 30,
    active            BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at        TIMESTAMPTZ,
    created_on        TIMESTAMPTZ NOT NULL,
    created_by        VARCHAR(36) NOT NULL,
    updated_on        TIMESTAMPTZ NOT NULL,
    updated_by        VARCHAR(36) NOT NULL
);
CREATE INDEX ix_doctor_user_id  ON doctor (user_id);
CREATE INDEX ix_doctor_cmp_code ON doctor (cmp_code);

-- M:N doctor ↔ clinic.branch
CREATE TABLE doctor_branch (
    doctor_id VARCHAR(36) NOT NULL REFERENCES doctor(id) ON DELETE CASCADE,
    branch_id VARCHAR(36) NOT NULL REFERENCES branch(id),  -- RESTRICT backstop
    PRIMARY KEY (doctor_id, branch_id)
);

-- M:N doctor ↔ catalog.vertical
CREATE TABLE doctor_vertical (
    doctor_id   VARCHAR(36) NOT NULL REFERENCES doctor(id) ON DELETE CASCADE,
    vertical_id VARCHAR(36) NOT NULL REFERENCES vertical(id),  -- RESTRICT backstop
    PRIMARY KEY (doctor_id, vertical_id)
);
-- revision = "0009_staff_doctor"  (≤ 32 chars: 17)
-- down_revision = "0008_clinic_office_closure"
```

> `"user"` va entre comillas: `user` es palabra reservada en Postgres y la tabla del template se llama así.

### `0010_staff_doctor_availability.py` (F2 — bloques concretos por fecha)

```sql
CREATE TABLE doctor_availability (
    id          VARCHAR(36) PRIMARY KEY,
    doctor_id   VARCHAR(36) NOT NULL REFERENCES doctor(id),  -- RESTRICT
    branch_id   VARCHAR(36) NOT NULL REFERENCES branch(id),  -- RESTRICT
    office_id   VARCHAR(36) NOT NULL REFERENCES office(id),  -- RESTRICT
    date        DATE NOT NULL,
    opens_at    TIME WITHOUT TIME ZONE NOT NULL,
    closes_at   TIME WITHOUT TIME ZONE NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at  TIMESTAMPTZ,
    created_on  TIMESTAMPTZ NOT NULL,
    created_by  VARCHAR(36) NOT NULL,
    updated_on  TIMESTAMPTZ NOT NULL,
    updated_by  VARCHAR(36) NOT NULL,
    CONSTRAINT ck_doctor_availability_closes_after_opens CHECK (closes_at > opens_at)
);
CREATE INDEX ix_doctor_availability_doctor_id      ON doctor_availability (doctor_id);
CREATE INDEX ix_doctor_availability_doctor_id_date ON doctor_availability (doctor_id, date);
-- NO day_of_week, NO is_available, NO recurrence (replaces Pattern+Override).
-- revision = "0010_staff_doctor_availability"  (≤ 32 chars: 30)
-- down_revision = "0009_staff_doctor"
```

**Sin `ON DELETE CASCADE`** en los FKs a `doctor`/`branch`/`office` de `doctor_availability` (son `RESTRICT` default), reforzando los guards de service y el backstop ante hard-deletes. La única excepción `CASCADE` son las tablas de asociación (`doctor_branch.doctor_id`, `doctor_vertical.doctor_id`), idéntico a `clinic.office_vertical.office_id`.

## Seed

Los **11 permisos** de `staff` ya están consolidados en [`_seed-and-roles.md`](../_seed-and-roles.md) (`MENU-STAFF`, `DOCTORS_READ/CREATE/UPDATE/DELETE`, `DOCTOR_AVAILABILITY_READ/WRITE`, `MY_DOCTOR_PROFILE_READ/WRITE`, `MY_AVAILABILITY_READ/WRITE`; `module="STAFF"`). **Nada de datos operativos que seedear**: los doctores los crea el admin de cada clínica (igual que `clinic` no seedea branches/offices ni `catalog` verticals/services).

F0 de `staff` introduce además el **helper genérico `_seed_role`** y los roles `DOCTOR` / `ASESOR` (subsets disponibles HOY; `SYSTEM` se difiere). Detalle exacto y código del helper en [`_seed-and-roles.md`](../_seed-and-roles.md#patches-sugeridos-a-appcoreseedpy):

- **`_seed_role(db, actor_id, role_name, role_description, permission_codes, all_permissions)`**: idempotente, hace `[p for p in all_permissions if p.code in permission_codes]` — los códigos que aún no existen (módulos futuros) se omiten silenciosamente, así que es a prueba de orden de implementación. Reemplaza el `_seed_admin_role` único del template.
- **`ADMIN`**: todos los permisos.
- **`DOCTOR`** (subset disponible hoy): `MENU-HOME`, `MENU-CATALOG` + `VERTICALS_READ`/`SERVICES_READ`/`PRODUCTS_READ`, clínica `*_READ` (`BRANCHES_READ`, `OFFICES_READ`, `OFFICE_HOURS_READ`, `OFFICE_CLOSURES_READ`), `MENU-STAFF`, `DOCTORS_READ`, `MY_DOCTOR_PROFILE_*`, `MY_AVAILABILITY_*`. (Los de `scheduling`/`crm` se suman al existir esos módulos; el `_seed_role` filtra los códigos inexistentes hoy.)
- **`ASESOR`** (subset disponible hoy): `MENU-HOME`, `MENU-CATALOG` + catálogo `*_READ`, `MENU-CLINIC` + `BRANCHES_READ` + `OFFICES_READ`, `DOCTORS_READ`, `DOCTOR_AVAILABILITY_READ`. (Crece al sumar `crm`/`conversations`/`scheduling`/`marketing`.)

El `seed()` invoca `_seed_role(...)` para ADMIN, DOCTOR y ASESOR tras `_seed_permissions`. El usuario bootstrap admin **no** crea perfil de doctor (ADR-002).

## Checklist de implementación (mapeado a fases F0–F3)

### F0 — Prep
- [ ] Agregar los 11 permisos de `staff` a `app/core/seed.py:SEED_PERMISSIONS` (ya consolidados en [`_seed-and-roles.md`](../_seed-and-roles.md)).
- [ ] Introducir el helper genérico `_seed_role` (reemplaza `_seed_admin_role`) y seedear `ADMIN` (todos), `DOCTOR` y `ASESOR` con el subset disponible hoy.
- [ ] Crear el esqueleto `backend/app/modules/staff/{models,schemas,repositories,services,routers}/` + `models/associations.py`.
- [ ] Registrar el módulo en `app/modules/__init__.py` (`from app.modules import admin, catalog, clinic, staff`).
- [ ] Incluir el aggregator router en `app/main.py` (`prefix="/staff"`).
- [ ] (Frontend F0) nav "Staff" → "Doctores" (`MENU-STAFF`) + ícono de sidebar; `endpoints.ts` (DOCTORS + availability + me); `types/staff.types.ts` (todas las interfaces espejo) — ver [`frontend.md`](frontend.md).
- [ ] Smoke test: login admin → el JWT contiene los 11 permisos de STAFF; `POST /staff/doctors/list` body vacío → `200` items vacíos.

### F1 — Doctor (+ M:N doctor_branch / doctor_vertical)
- [ ] `models/associations.py` (`doctor_branch`, `doctor_vertical`) + `models/doctor.py` + migration `0009_staff_doctor` (`down_revision="0008_clinic_office_closure"`).
- [ ] `schemas/doctor.py` (`DoctorUserCreate`, `DoctorCreate` nested, `DoctorUpdate`, `DoctorItem`, `DoctorDetail`, `DoctorOption`, `DoctorCreatedResponse`) con validators de duplicados.
- [ ] `repositories/doctor.py`: `ALLOWED_FIELDS`, `get_by_user_id`, `get_full` (con `with_loader_criteria` filtrando branches/verticals soft-deleted), `list_active(branch_id, vertical_id)`, `count_branches_map`, `count_verticals_map`.
- [ ] Agregar `branch_repository.get_by_ids` a `clinic` si no existe (cambio aditivo).
- [ ] `services/doctor.py`: `create` NESTED (User + role DOCTOR + Doctor en una tx; `generated_password`), `_resolve_branches`/`_resolve_verticals`, reload-via-`get_full`, `soft_delete` (NO toca User).
- [ ] `routers/doctor.py`: CRUD + `/active?branch_id=&vertical_id=` (lista cruda); `PUT` para update.
- [ ] (Frontend F1) lista `/staff/doctors` + drawer de creación NESTED; página detalle `/staff/doctors/{id}` con tabs (Perfil + Auditoría; Disponibilidad placeholder) — ver [`ui.md`](ui.md).
- [ ] Test create NESTED: `POST /doctors` sin `user.password` → `201` con `generated_password`; el User nace con role DOCTOR.
- [ ] Test email duplicado: `POST /doctors` con email tomado → `409 EMAIL_TAKEN` (y NO se crea Doctor huérfano).
- [ ] Test M:N: crear con `branch_ids`/`vertical_ids` → `DoctorDetail.branches`/`.verticals` los listan; soft-delete un branch/vertical → desaparece de detail y de los counts.
- [ ] Test soft-delete: `DELETE /doctors/{id}` → `204`; el `User` sigue activo (ADR-002).

### F2 — DoctorAvailability (bloques concretos por fecha)
- [ ] `models/doctor_availability.py` (CHECK `closes_at>opens_at`, índice `(doctor_id, date)`) + migration `0010_staff_doctor_availability` (`down_revision="0009_staff_doctor"`).
- [ ] `schemas/doctor_availability.py` (`Create` con validator `closes_at>opens_at`, `BulkCreate {blocks}`, `Update`, `Item` denormalizado).
- [ ] `repositories/doctor_availability.py`: `list_for_doctor(from, to)`, `list_for_doctor_on_date`.
- [ ] `services/doctor_availability.py`: `_validate_block` (invariantes 1-3 con `OFFICE_NOT_IN_BRANCH`/`DOCTOR_NOT_IN_BRANCH`/`AVAILABILITY_OVERLAP`), `bulk_create` (valida también entre bloques del body), `update_block` (merge + re-valida + ownership), `delete_block` (ownership), `list_for_doctor` con denormalización branch_name/office_code/office_name.
- [ ] `routers/doctor_availability.py`: `GET ?from=&to=`, `POST` bulk, `PUT`, `DELETE` anidados bajo `/doctors/{id}/availability`.
- [ ] (Frontend F2) tab "Disponibilidad" = grilla semanal tipo calendario (el componente más pesado del proyecto) — ver [`ui.md`](ui.md).
- [ ] Test invariante 1: bloque con `office_id` de otra sede → `400 OFFICE_NOT_IN_BRANCH`.
- [ ] Test invariante 2: bloque en una sede a la que el doctor no está asignado → `400 DOCTOR_NOT_IN_BRANCH`.
- [ ] Test invariante 3: dos bloques solapados en la misma fecha (existente vs entrante, y dentro del body) → `400 AVAILABILITY_OVERLAP`; adyacentes (`[08-13)` + `[13-20)`) OK.
- [ ] Test ownership: `PUT`/`DELETE` de un `block_id` de otro doctor → `404 AVAILABILITY_NOT_FOUND`.
- [ ] Test rango: `GET ?from=&to=` filtra `date` BETWEEN; `closes_at <= opens_at` en el body → `422`.

### F3 — Self-service `/me`
- [ ] `services/me.py`: `_require_my_doctor` (`get_by_user_id` → `403 NOT_A_DOCTOR`), `get_my_doctor`, `update_my_doctor` (solo `cmp_code`/`bio`/`photo`/`signature`/`slot_duration`), `list_my_availability`, `create/update/delete_my_availability` (delegan en `doctor_availability` service con `doctor.id`).
- [ ] `schemas/doctor.py`: agregar `DoctorSelfUpdate` (subset de `DoctorUpdate` sin `branch_ids`/`vertical_ids`/`active`).
- [ ] `routers/me.py`: `GET`/`PUT /me/doctor` + `GET`/`POST`/`PUT`/`DELETE /me/availability/*` con permisos `MY_*`.
- [ ] (Frontend F3) "Mi perfil" + "Mi agenda" (reusa el calendario de F2 en modo self) — ver [`ui.md`](ui.md).
- [ ] Test `/me`: user con role DOCTOR y perfil → `GET /me/doctor` `200`; user sin perfil → `403 NOT_A_DOCTOR`.
- [ ] Test scoping: el doctor logueado solo ve/edita SU disponibilidad vía `/me`; no puede tocar otra vía `/me/availability/{block_id}` ajeno (resuelve por su propio `doctor.id`).
- [ ] Test `PUT /me/doctor` con `branch_ids` en el body → se ignoran (no reasigna sedes).
