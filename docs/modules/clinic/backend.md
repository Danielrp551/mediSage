# Módulo `clinic` — Backend deep-dive

> **Última actualización**: 2026-05-29
> **Audiencia**: developer implementando `backend/app/modules/clinic/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`../../diagrams/er-clinic.puml`](../../diagrams/er-clinic.puml) y la ficha de catálogo [`../catalog/backend.md`](../catalog/backend.md) — `clinic` referencia `catalog.Vertical` por M:N.

> **Convenciones alineadas al código shipped de `catalog`** (el overview previo de clinic — ahora consolidado en [`README.md`](README.md) — proponía otras que quedan deprecadas):
>
> 1. **`PUT` para updates completos** (no `PATCH`). El catalog shipped usa `PUT /services/{id}` — `clinic` sigue eso. El borrador previo listaba `PATCH`; queda **deprecado**.
> 2. **`/active` para dropdowns** (no `/options`). El template usa `/active` (`ENDPOINTS.ROLES.ACTIVE`, catalog `/verticals/active`). El borrador listaba `/options`; queda **deprecado**. Excepción: el bulk de horarios se queda en `PUT /offices/{id}/operating-hours`.
> 3. **`/active` devuelve lista cruda** (`response_model=list[...]`), sin envelope `SingleResponse`, igual que `catalog`.

## Estructura de archivos a crear

```
backend/app/modules/clinic/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── associations.py          # office_vertical (M:N → catalog.vertical)
│   ├── branch.py
│   ├── office.py
│   ├── office_operating_hours.py
│   └── office_closure.py
├── schemas/
│   ├── __init__.py
│   ├── branch.py
│   ├── office.py
│   ├── office_operating_hours.py
│   └── office_closure.py
├── repositories/
│   ├── __init__.py
│   ├── branch.py
│   ├── office.py
│   ├── office_operating_hours.py
│   └── office_closure.py
├── services/
│   ├── __init__.py
│   ├── branch.py
│   ├── office.py
│   ├── office_operating_hours.py
│   └── office_closure.py
└── routers/
    ├── __init__.py              # aggregator: prefix="/clinic"
    ├── branch.py
    ├── office.py
    ├── office_operating_hours.py
    └── office_closure.py
```

**Sí hay `models/associations.py`** (a diferencia de `catalog`, que no tiene M:N propias): `office_vertical` es propiedad de `clinic` — referencia `catalog.vertical.id` pero la tabla de asociación vive aquí. Esto sigue la convención del template (`admin/models/associations.py` aloja `user_role`, `role_permission`, `user_permission`).

Registrar el módulo en `app/modules/__init__.py`:

```python
from app.modules import admin, catalog, clinic  # noqa: F401
```

Y registrar el aggregator del router en `app/main.py` (igual que catalog: un solo `include_router`):

```python
from app.modules.clinic.routers import router as clinic_router

app.include_router(clinic_router)  # prefix="/api/v1" + "/clinic" interno
```

El aggregator `routers/__init__.py` replica el patrón de `catalog/routers/__init__.py`:

```python
from fastapi import APIRouter

from app.modules.clinic.routers.branch import router as branch_router
from app.modules.clinic.routers.office import router as office_router
from app.modules.clinic.routers.office_closure import router as closure_router
from app.modules.clinic.routers.office_operating_hours import router as hours_router

router = APIRouter(prefix="/clinic")
router.include_router(branch_router)
router.include_router(office_router)
# hours + closures cuelgan de /offices/{office_id}/... — ver routers abajo
router.include_router(hours_router)
router.include_router(closure_router)

__all__ = ["router"]
```

## Models — SQLAlchemy 2.0

### `models/associations.py` — tabla M:N `office_vertical`

```python
"""
Many-to-many association tables for the clinic module. Kept in a single
file so SQLAlchemy sees them before the related models import (template
convention — admin/models/associations.py does the same with user_role).

`office_vertical` links an Office to the catalog Verticals it is fit to
host. The FK to `vertical.id` is RESTRICT (default, no ondelete) — a
hard-deleted vertical must not silently orphan the association; catalog's
soft-delete is the normal path and is filtered out at query time, not
enforced here (no coupling to catalog's delete guard).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

office_vertical = Table(
    "office_vertical",
    Base.metadata,
    Column(
        "office_id",
        String(36),
        ForeignKey("office.id", ondelete="CASCADE"),
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

**Por qué `office_id` es `CASCADE` pero `vertical_id` es `RESTRICT`**: borrar un office (soft-delete normal; el hard-delete solo lo hace una migración) puede limpiar sus filas de asociación sin coordinación cross-module. Pero un `vertical` se borra desde `catalog` — si alguien intenta hard-delete de un vertical aún asociado a offices, el FK `RESTRICT` es el backstop que lo bloquea. El path normal (soft-delete del vertical) **no** toca esta tabla: las filas quedan y se filtran al hidratar (ver "Filtrar verticales soft-deleted" abajo). Esto evita acoplar el delete guard de `catalog.Vertical` a `clinic`.

### `models/branch.py`

```python
"""
Branch = a physical clinic site (sede). Root of the clinic hierarchy, no
domain FK. Carries a structured address (not free text) to enable future
"nearest branch" filtering in the bot and map integration. `code` is a
stable slug used in internal URLs and by bots — never renamed once issued.

`timezone` is an IANA name per branch (multi-country ready). It only matters
when scheduling resolves a local pattern time to a UTC instant; most instants
(closures, appointments) travel as timestamptz and convert in the browser.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.clinic.models.office import Office


class Branch(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "branch"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # ── Structured address ──
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="PE")
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Geo (optional) ──
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)

    # ── Contact ──
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Time ──
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="America/Lima")

    # Children. `lazy="raise"` keeps accidental N+1 loud — offices_count is
    # computed with explicit batch queries in the service layer, not via this.
    offices: Mapped[list[Office]] = relationship(back_populates="branch", lazy="raise")
```

### `models/office.py`

```python
"""
Office = a consulting room (consultorio) inside a Branch. Declares which
catalog Verticals it is fit to host (M:N office_vertical) so scheduling can
filter offices apt for a requested product. `code` is unique per branch
((branch_id, code)) — the same code can repeat across branches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.clinic.models.associations import office_vertical
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.vertical import Vertical
    from app.modules.clinic.models.branch import Branch
    from app.modules.clinic.models.office_closure import OfficeClosure
    from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours


class Office(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "office"
    __table_args__ = (UniqueConstraint("branch_id", "code", name="uq_office_branch_code"),)

    branch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("branch.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    room_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    branch: Mapped[Branch] = relationship(back_populates="offices", lazy="raise")

    # M:N with catalog.Vertical. `lazy="raise"` — the apt verticals are loaded
    # explicitly with selectinload + a deleted_at filter (see repository).
    verticals: Mapped[list[Vertical]] = relationship(
        secondary=office_vertical, lazy="raise"
    )

    # Children. `lazy="raise"` — patterns/closures are loaded per-office on
    # demand (their own endpoints), never eagerly with the office list.
    operating_hours: Mapped[list[OfficeOperatingHours]] = relationship(
        back_populates="office", lazy="raise"
    )
    closures: Mapped[list[OfficeClosure]] = relationship(
        back_populates="office", lazy="raise"
    )
```

> **Nota M:N sin `back_populates`**: `office_vertical` es *uni-direccional* desde `clinic`. `catalog.Vertical` **NO** declara `offices` ni conoce esta asociación — eso mantiene `catalog` desacoplado de `clinic` (catalog no debe importar de clinic). El template ya tiene relaciones M:N bidireccionales (`Role.permissions`/`Permission.roles`), pero aquí la dirección importa: `clinic` depende de `catalog`, no al revés.

### `models/office_operating_hours.py`

```python
"""
OfficeOperatingHours = one recurring weekly time block of an office. An
office can have SEVERAL rows per day (morning + afternoon with a lunch gap);
there is deliberately NO unique on (office_id, day_of_week).

`day_of_week` follows the Python `datetime.weekday()` convention:
0 = Monday ... 6 = Sunday (NOT Postgres EXTRACT(DOW), which is 0 = Sunday).
The scheduling code is Python, so using the host-language convention avoids
off-by-one bugs. `opens_at`/`closes_at` are naive `time` (no TZ) interpreted
in `office.branch.timezone`. CHECK closes_at > opens_at: a block never
crosses midnight (model that as two blocks on two days).
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.clinic.models.office import Office


class OfficeOperatingHours(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "office_operating_hours"
    __table_args__ = (
        CheckConstraint("closes_at > opens_at", name="ck_office_hours_closes_after_opens"),
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_office_hours_day_of_week_range",
        ),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("office.id"), nullable=False, index=True
    )
    # 0=Mon .. 6=Sun (Python datetime.weekday()).
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    closes_at: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)

    office: Mapped[Office] = relationship(back_populates="operating_hours", lazy="raise")
```

### `models/office_closure.py`

```python
"""
OfficeClosure = an ad-hoc exception to the weekly pattern, covering BOTH
cases with one schema via `is_closed`:
  - is_closed=True  → office NOT available in the range (holiday, maintenance);
                      overrides the pattern.
  - is_closed=False → office IS available even if the pattern says otherwise
                      (e.g. open one Sunday on demand).

`starts_at`/`ends_at` are timestamptz (UTC on disk, ISO 8601 with offset in
JSON). CHECK ends_at > starts_at. scheduling interprets `is_closed` when it
combines closures with the recurring pattern.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.clinic.models.office import Office


class OfficeClosure(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "office_closure"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_office_closure_ends_after_starts"),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("office.id"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    office: Mapped[Office] = relationship(back_populates="closures", lazy="raise")
```

### `models/__init__.py`

```python
"""
Importing models here ensures SQLAlchemy registers them on `Base.metadata`
before Alembic reads the schema. Import associations first so the M:N table
exists before Office references it.
"""

from app.modules.clinic.models.associations import office_vertical
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.modules.clinic.models.office_closure import OfficeClosure
from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours

__all__ = [
    "Branch",
    "Office",
    "OfficeClosure",
    "OfficeOperatingHours",
    "office_vertical",
]
```

**Lazy strategy**: como en `catalog`, todas las relaciones en `lazy="raise"`. La M:N `Office.verticals` y los hijos (`operating_hours`, `closures`) se cargan con `selectinload(...)` explícito en el repo, nunca implícitamente.

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (oficiales FastAPI/Pydantic v2 — ver skill `fastapi`, idénticas a [`../catalog/backend.md`](../catalog/backend.md#schemas-pydantic-v2--completos)):
>
> 1. **No usar Ellipsis (`...`)** en `Field(...)`. Campo sin `default=` ya es obligatorio.
> 2. **`Annotated`** solo para parámetros HTTP (`Query`, `Path`) en routers.
> 3. **Validators**: `@field_validator` single-field, `@model_validator(mode="after")` cross-field.
> 4. **Mensajes de validator en inglés** (van al detalle 422). El texto user-facing en español vive en el Zod del frontend.

### `schemas/branch.py`

```python
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
# Cheap IANA sanity check ("Area/Location"); full validation is the OS tz db's
# job, done by scheduling when it resolves a local time.
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z]+/[A-Za-z_+\-/]+$")


class BranchCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    address_line: str = Field(min_length=1, max_length=255)
    district: str | None = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str = Field(default="PE", min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="America/Lima", min_length=3, max_length=60)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be a lowercase slug: letters/digits/_, "
                "start with a letter, end with letter or digit (3-40 chars)"
            )
        return v

    @field_validator("country")
    @classmethod
    def _iso_country(cls, v: str) -> str:
        v = v.upper()
        if not COUNTRY_PATTERN.fullmatch(v):
            raise ValueError("country must be ISO 3166-1 alpha-2 (e.g. PE, MX)")
        return v

    @field_validator("timezone")
    @classmethod
    def _iana_tz(cls, v: str) -> str:
        if not TIMEZONE_PATTERN.fullmatch(v):
            raise ValueError("timezone must be an IANA name like America/Lima")
        return v


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    district: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, min_length=3, max_length=60)
    active: bool | None = None
    # NOT updatable: code (stable slug used in URLs and by bots).

    @field_validator("country")
    @classmethod
    def _iso_country(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.upper()
        if not COUNTRY_PATTERN.fullmatch(v):
            raise ValueError("country must be ISO 3166-1 alpha-2 (e.g. PE, MX)")
        return v

    @field_validator("timezone")
    @classmethod
    def _iana_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not TIMEZONE_PATTERN.fullmatch(v):
            raise ValueError("timezone must be an IANA name like America/Lima")
        return v


class BranchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    address_line: str
    district: str | None
    city: str
    region: str | None
    country: str
    postal_code: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    phone: str | None
    email: str | None
    timezone: str
    active: bool
    offices_count: int  # denormalized for table rows (avoids a drawer fetch)
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class BranchDetail(BranchItem):
    """Same shape as Item — a branch has no extra relations to resolve in the
    drawer (offices live behind the Offices list filtered by branch_id)."""


class BranchOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    city: str | None = None
    timezone: str | None = None
```

### `schemas/office.py`

```python
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.clinic.schemas.branch import BranchOption

# Office codes are short identifiers ("C-03", "ESTETICA-01"): uppercase
# letters/digits with - and _. Looser than catalog slugs on purpose.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,38}[A-Za-z0-9]$")


class OfficeCreate(BaseModel):
    branch_id: str = Field(min_length=1)
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    room_number: str | None = Field(default=None, max_length=20)
    floor: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    vertical_ids: list[str] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be 2-40 chars: letters/digits/-/_, "
                "start and end with a letter or digit"
            )
        return v

    @field_validator("vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("vertical_ids must not contain duplicates")
        return v


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    room_number: str | None = Field(default=None, max_length=20)
    floor: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    # Full M:N replace when present; omit to leave the apt verticals untouched.
    vertical_ids: list[str] | None = None
    active: bool | None = None
    # NOT updatable: branch_id (would move the office between sites and orphan
    # its hours/closures coordinates), code (stable per-branch identifier).

    @field_validator("vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("vertical_ids must not contain duplicates")
        return v


class OfficeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    branch_id: str
    branch_name: str  # denormalized for table rows (avoids a drawer fetch)
    code: str
    name: str
    room_number: str | None
    floor: str | None
    description: str | None
    active: bool
    verticals_count: int  # denormalized count of apt (non-deleted) verticals
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class OfficeDetail(OfficeItem):
    branch: BranchOption
    verticals: list[VerticalOption]  # soft-deleted verticals filtered out


class OfficeOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    branch_id: str
    code: str
    name: str
```

### `schemas/office_operating_hours.py`

```python
from __future__ import annotations

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_DAY = 0  # Monday (Python datetime.weekday())
MAX_DAY = 6  # Sunday


class OfficeOperatingHoursItem(BaseModel):
    """One weekly block. Used both in the bulk replace body and in the GET
    response. `id` is optional so the same shape serves input and output."""

    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    day_of_week: int = Field(ge=MIN_DAY, le=MAX_DAY)
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def _closes_after_opens(self) -> OfficeOperatingHoursItem:
        # Mirrors the DB CHECK (closes_at > opens_at). A block never crosses
        # midnight; if business needs that, model two blocks on two days.
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be later than opens_at")
        return self


class OfficeOperatingHoursReplace(BaseModel):
    """Body of the atomic bulk PUT /offices/{id}/operating-hours. The full
    weekly pattern is replaced as one aggregate — no per-block CRUD."""

    hours: list[OfficeOperatingHoursItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_overlaps(self) -> OfficeOperatingHoursReplace:
        # Multiple blocks per day are allowed (morning + afternoon), but two
        # blocks on the same day must not overlap — that's an inconsistent
        # pattern the bulk replace should reject up front.
        by_day: dict[int, list[tuple[time, time]]] = {}
        for h in self.hours:
            by_day.setdefault(h.day_of_week, []).append((h.opens_at, h.closes_at))
        for day, blocks in by_day.items():
            blocks.sort()
            for (_, prev_close), (next_open, _) in zip(blocks, blocks[1:]):
                if next_open < prev_close:
                    raise ValueError(
                        f"overlapping blocks on day_of_week={day} "
                        "(Python weekday: 0=Mon)"
                    )
        return self
```

### `schemas/office_closure.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class OfficeClosureCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    is_closed: bool = True
    reason: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _ends_after_starts(self) -> OfficeClosureCreate:
        # Mirrors the DB CHECK (ends_at > starts_at).
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class OfficeClosureItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    office_id: str
    starts_at: datetime
    ends_at: datetime
    is_closed: bool
    reason: str
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class OfficeClosureDetail(OfficeClosureItem):
    """Same shape as Item — a closure has no relations to resolve."""
```

> **Closures sin variante `Update`** (decisión confirmada): una excepción es una unidad atómica pequeña (rango + flag + razón). Para corregirla se **elimina y se recrea** — no hay `PUT /closures/{id}` ni schema `OfficeClosureUpdate`. Mantiene el set de endpoints chico (`POST` + `DELETE`) y coherente con `ui.md`/`frontend.md` (que también modelan editar = borrar + recrear).

## Repositories

`ALLOWED_FIELDS` es el whitelist de columnas filtrable / ordenable desde el frontend (ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md#queryrequest-y-baserepositoryget_paginated)).

```python
# repositories/branch.py
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.shared.base_repository import BaseRepository


class BranchRepository(BaseRepository[Branch]):
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "city", "region", "country",
        "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Branch)

    async def get_by_code(self, db: AsyncSession, code: str) -> Branch | None:
        result = await db.execute(
            select(Branch).where(Branch.code == code, Branch.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Branch]:
        result = await db.execute(
            select(Branch)
            .where(Branch.active.is_(True), Branch.deleted_at.is_(None))
            .order_by(Branch.name.asc())
        )
        return list(result.scalars().all())

    async def count_active_offices(self, db: AsyncSession, branch_id: str) -> int:
        """Count non-deleted offices under one branch (delete guard)."""
        result = await db.execute(
            select(func.count(Office.id)).where(
                Office.branch_id == branch_id,
                Office.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_active_offices_map(
        self, db: AsyncSession, branch_ids: list[str]
    ) -> dict[str, int]:
        """Batch office counts for a page of branches — one query, no N+1."""
        if not branch_ids:
            return {}
        result = await db.execute(
            select(Office.branch_id, func.count(Office.id))
            .where(Office.branch_id.in_(branch_ids), Office.deleted_at.is_(None))
            .group_by(Office.branch_id)
        )
        return {row[0]: row[1] for row in result.all()}


branch_repository = BranchRepository()
```

```python
# repositories/office.py
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.catalog.models.vertical import Vertical
from app.modules.clinic.models.associations import office_vertical
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.shared.base_repository import BaseRepository


class OfficeRepository(BaseRepository[Office]):
    ALLOWED_FIELDS: set[str] = {
        "branch_id", "code", "name", "floor",
        "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Office)

    async def get_by_branch_and_code(
        self, db: AsyncSession, branch_id: str, code: str
    ) -> Office | None:
        result = await db.execute(
            select(Office).where(
                Office.branch_id == branch_id,
                Office.code == code,
                Office.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, office_id: str) -> Office | None:
        # Eager-load the parent branch and the apt verticals, filtering out
        # soft-deleted verticals via `with_loader_criteria` so the M:N load
        # respects catalog's soft-delete WITHOUT clinic coupling to catalog's
        # delete guard (the office_vertical row may still exist; we just don't
        # surface a dead vertical).
        return await self.get_by_id(
            db,
            office_id,
            load=(
                selectinload(Office.branch),
                selectinload(Office.verticals),
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
    ) -> list[Office]:
        # No eager-load: the only consumer maps rows to OfficeOption, which
        # never touches branch/verticals. `vertical_id` filters via an EXISTS
        # join on office_vertical (the office must be apt for that vertical
        # AND the vertical must be alive).
        stmt = (
            select(Office)
            .where(Office.active.is_(True), Office.deleted_at.is_(None))
            .order_by(Office.code.asc())
        )
        if branch_id is not None:
            stmt = stmt.where(Office.branch_id == branch_id)
        if vertical_id is not None:
            stmt = stmt.where(
                select(office_vertical.c.office_id)
                .join(Vertical, Vertical.id == office_vertical.c.vertical_id)
                .where(
                    office_vertical.c.office_id == Office.id,
                    office_vertical.c.vertical_id == vertical_id,
                    Vertical.deleted_at.is_(None),
                )
                .exists()
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_apt_verticals_map(
        self, db: AsyncSession, office_ids: list[str]
    ) -> dict[str, int]:
        """Batch count of apt, non-deleted verticals per office — one query,
        no N+1. Powers OfficeItem.verticals_count. Joins through the M:N and
        filters deleted verticals so disabled/removed catalog rows don't count."""
        if not office_ids:
            return {}
        result = await db.execute(
            select(office_vertical.c.office_id, func.count(office_vertical.c.vertical_id))
            .join(Vertical, Vertical.id == office_vertical.c.vertical_id)
            .where(
                office_vertical.c.office_id.in_(office_ids),
                Vertical.deleted_at.is_(None),
            )
            .group_by(office_vertical.c.office_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def branch_name_map(
        self, db: AsyncSession, branch_ids: list[str]
    ) -> dict[str, str]:
        """Batch branch names for the denormalized OfficeItem.branch_name."""
        if not branch_ids:
            return {}
        result = await db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids))
        )
        return {row[0]: row[1] for row in result.all()}


office_repository = OfficeRepository()
```

```python
# repositories/office_operating_hours.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours
from app.shared.base_repository import BaseRepository


class OfficeOperatingHoursRepository(BaseRepository[OfficeOperatingHours]):
    # Not filtered/sorted dynamically — read via list_for_office, written via
    # the bulk replace. ALLOWED_FIELDS stays empty (no /list endpoint).
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(OfficeOperatingHours)

    async def list_for_office(
        self, db: AsyncSession, office_id: str
    ) -> list[OfficeOperatingHours]:
        result = await db.execute(
            select(OfficeOperatingHours)
            .where(
                OfficeOperatingHours.office_id == office_id,
                OfficeOperatingHours.deleted_at.is_(None),
            )
            .order_by(
                OfficeOperatingHours.day_of_week.asc(),
                OfficeOperatingHours.opens_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def soft_delete_for_office(self, db: AsyncSession, office_id: str) -> None:
        """Retire ALL current live blocks of an office, used by the atomic bulk
        replace right before inserting the new set. Soft-delete (not hard) keeps
        the entity uniform with the rest of the template — every model carries
        SoftDeleteMixin and BaseRepository reads filter `deleted_at IS NULL`, so
        the retired pattern simply disappears from reads. Weekly patterns change
        rarely, so row accumulation is negligible, and the retired rows double
        as a cheap audit trail of past schedules."""
        rows = await self.list_for_office(db, office_id)
        for row in rows:
            await self.soft_delete(db, row)


office_operating_hours_repository = OfficeOperatingHoursRepository()
```

```python
# repositories/office_closure.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.office_closure import OfficeClosure
from app.shared.base_repository import BaseRepository


class OfficeClosureRepository(BaseRepository[OfficeClosure]):
    ALLOWED_FIELDS: set[str] = {"is_closed", "starts_at", "ends_at", "created_on"}

    def __init__(self) -> None:
        super().__init__(OfficeClosure)

    async def list_for_office(
        self,
        db: AsyncSession,
        office_id: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[OfficeClosure]:
        # Range overlap: a closure is in range if it starts before `to` AND
        # ends after `from` (half-open windows handled by the callers).
        stmt = (
            select(OfficeClosure)
            .where(
                OfficeClosure.office_id == office_id,
                OfficeClosure.deleted_at.is_(None),
            )
            .order_by(OfficeClosure.starts_at.asc())
        )
        if date_to is not None:
            stmt = stmt.where(OfficeClosure.starts_at < date_to)
        if date_from is not None:
            stmt = stmt.where(OfficeClosure.ends_at > date_from)
        result = await db.execute(stmt)
        return list(result.scalars().all())


office_closure_repository = OfficeClosureRepository()
```

## API contracts

Todos los endpoints usan los envelopes del template (idénticos a [`../catalog/backend.md`](../catalog/backend.md#api-contracts)):
- **Single**: `{ "success": true, "data": <T> }`
- **Paginated**: `{ "success": true, "data": { "items": [...], "total": N, "skip": 0, "limit": 10 } }`
- **Lista cruda** (endpoints `/active`): el body es directamente `[...]` (sin envelope), igual que `catalog`.
- **Error**: `{ "success": false, "detail": "...", "code"?: "...", "errors"?: [...] }`

Prefijo común: `/api/v1/clinic/`. Listados paginados con `POST /<recurso>/list` + `QueryRequest`.

### Branch

#### `POST /api/v1/clinic/branches/list`

**Request** (`QueryRequest`):
```json
{
  "pagination": { "skip": 0, "limit": 10 },
  "sorting":    { "sort_by": "name", "sort_order": "asc" },
  "filters": {
    "filters": [
      { "operator": "AND", "conditions": [
        { "field": "city", "operator": "eq", "value": "Lima" },
        { "field": "active", "operator": "eq", "value": true }
      ] }
    ]
  }
}
```

**Response** (`PaginatedResponse[BranchItem]`):
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "1a2b...",
        "code": "lima_centro",
        "name": "Sede Lima Centro",
        "address_line": "Av. Larco 1234",
        "district": "Miraflores",
        "city": "Lima",
        "region": "Lima",
        "country": "PE",
        "postal_code": "15074",
        "latitude": "-12.121200",
        "longitude": "-77.029700",
        "phone": "+51 1 555 1234",
        "email": "limacentro@medisage.pe",
        "timezone": "America/Lima",
        "active": true,
        "offices_count": 6,
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

#### `POST /api/v1/clinic/branches`

**Request** (`BranchCreate`):
```json
{
  "code": "lima_centro",
  "name": "Sede Lima Centro",
  "address_line": "Av. Larco 1234",
  "district": "Miraflores",
  "city": "Lima",
  "region": "Lima",
  "country": "PE",
  "postal_code": "15074",
  "latitude": "-12.121200",
  "longitude": "-77.029700",
  "phone": "+51 1 555 1234",
  "email": "limacentro@medisage.pe",
  "timezone": "America/Lima"
}
```

**Response** `201`:
```json
{ "success": true, "data": { "id": "1a2b...", "code": "lima_centro", "offices_count": 0, "...": "..." } }
```

**Error 409** (code duplicado):
```json
{ "success": false, "detail": "Branch with code 'lima_centro' already exists", "code": "BRANCH_CODE_TAKEN" }
```

#### `GET /api/v1/clinic/branches/{id}` → `SingleResponse[BranchDetail]`

#### `PUT /api/v1/clinic/branches/{id}`

**Request**: cualquier subset de `BranchUpdate`. `code` no es actualizable (`BranchUpdate` no lo declara; el server lo descarta belt-and-suspenders).

#### `DELETE /api/v1/clinic/branches/{id}` → soft-delete

**Response 204** sin body.

**Error 409** si hay offices activos asociados:
```json
{
  "success": false,
  "detail": "Cannot delete branch with 3 office(s) still attached. Delete its offices first.",
  "code": "BRANCH_HAS_ACTIVE_CHILDREN"
}
```

#### `GET /api/v1/clinic/branches/active`

**Response**: lista cruda `list[BranchOption]` (sin envelope):
```json
[
  { "id": "1a2b...", "code": "lima_centro", "name": "Sede Lima Centro", "city": "Lima", "timezone": "America/Lima" },
  { "id": "3c4d...", "code": "trujillo", "name": "Sede Trujillo", "city": "Trujillo", "timezone": "America/Lima" }
]
```

### Office

#### `POST /api/v1/clinic/offices/list`

**Filtros típicos** (por sede):
```json
{
  "pagination": { "skip": 0, "limit": 10 },
  "sorting": { "sort_by": "code", "sort_order": "asc" },
  "filters": {
    "filters": [
      { "operator": "AND", "conditions": [
        { "field": "branch_id", "operator": "eq", "value": "1a2b..." }
      ] }
    ]
  }
}
```

**Response**: items con `branch_name` y `verticals_count` denormalizados para evitar joins en el frontend.
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "9f8e...",
        "branch_id": "1a2b...",
        "branch_name": "Sede Lima Centro",
        "code": "C-03",
        "name": "Consultorio 3 — Dental",
        "room_number": "12",
        "floor": "2",
        "description": "Sillón dental + rayos X",
        "active": true,
        "verticals_count": 2,
        "created_on": "2026-05-29T14:23:10+00:00",
        "created_by": "...",
        "created_by_user": { "...": "..." },
        "updated_on": "2026-05-29T14:23:10+00:00",
        "updated_by": "...",
        "updated_by_user": { "...": "..." }
      }
    ],
    "total": 1, "skip": 0, "limit": 10
  }
}
```

#### `POST /api/v1/clinic/offices`

**Request** (`OfficeCreate`) — incluye `vertical_ids` para la M:N:
```json
{
  "branch_id": "1a2b...",
  "code": "C-03",
  "name": "Consultorio 3 — Dental",
  "room_number": "12",
  "floor": "2",
  "description": "Sillón dental + rayos X",
  "vertical_ids": ["8c5a...", "9d6b..."]
}
```

**Error 404** si `branch_id` no existe:
```json
{ "success": false, "detail": "Branch not found", "code": "BRANCH_NOT_FOUND" }
```

**Error 400** si algún `vertical_id` no existe o está soft-deleted:
```json
{ "success": false, "detail": "Unknown vertical(s): 9d6b..." }
```

**Error 409** si `(branch_id, code)` ya existe:
```json
{
  "success": false,
  "detail": "Office with code 'C-03' already exists in this branch",
  "code": "OFFICE_CODE_TAKEN"
}
```

**Response 201** (`SingleResponse[OfficeDetail]`) — incluye `branch` (BranchOption) + `verticals` (list[VerticalOption], soft-deleted filtradas):
```json
{
  "success": true,
  "data": {
    "id": "9f8e...",
    "branch_id": "1a2b...",
    "branch_name": "Sede Lima Centro",
    "branch": { "id": "1a2b...", "code": "lima_centro", "name": "Sede Lima Centro", "city": "Lima", "timezone": "America/Lima" },
    "code": "C-03",
    "name": "Consultorio 3 — Dental",
    "room_number": "12",
    "floor": "2",
    "description": "Sillón dental + rayos X",
    "active": true,
    "verticals_count": 2,
    "verticals": [
      { "id": "8c5a...", "code": "dental", "name": "Dental", "color": "#3B82F6", "icon": "ToothRegular" },
      { "id": "9d6b...", "code": "estetica_facial", "name": "Estética facial", "color": "#FF6B6B", "icon": "Sparkle24Regular" }
    ],
    "...": "audit fields"
  }
}
```

#### `GET /api/v1/clinic/offices/{id}` → `SingleResponse[OfficeDetail]`

Incluye `branch` y `verticals` resueltos (verticales soft-deleted excluidas vía `with_loader_criteria`, ver repo).

#### `PUT /api/v1/clinic/offices/{id}`

**Request** (`OfficeUpdate`): subset; `vertical_ids` presente = **reemplazo total** de la M:N; ausente = se dejan las verticales tal cual.
```json
{
  "name": "Consultorio 3 — Dental y Estética",
  "vertical_ids": ["8c5a...", "9d6b...", "7e2f..."]
}
```

`branch_id` y `code` no son actualizables (`OfficeUpdate` no los declara).

#### `DELETE /api/v1/clinic/offices/{id}` → soft-delete

**Response 204**. No hay guard de children por horarios/closures (son value aggregates del office, no entidades de otros módulos). Las filas `office_vertical` quedan (la M:N no estorba un soft-delete); `scheduling` filtra offices soft-deleted automáticamente vía `BaseRepository`.

#### `GET /api/v1/clinic/offices/active?branch_id=&vertical_id=`

Ambos query params opcionales. `branch_id` filtra por sede; `vertical_id` filtra offices **aptos** para esa vertical (EXISTS join sobre `office_vertical`, excluyendo verticales soft-deleted). Devuelve lista cruda `list[OfficeOption]`:
```json
[
  { "id": "9f8e...", "branch_id": "1a2b...", "code": "C-03", "name": "Consultorio 3 — Dental" },
  { "id": "a1b2...", "branch_id": "1a2b...", "code": "C-04", "name": "Consultorio 4 — Estética" }
]
```

### OfficeOperatingHours (bulk)

#### `GET /api/v1/clinic/offices/{id}/operating-hours`

**Permiso**: `OFFICE_HOURS_READ`. Lista los bloques del patrón ordenados por día → hora de apertura.

**Response** `SingleResponse[list[OfficeOperatingHoursItem]]`:
```json
{
  "success": true,
  "data": [
    { "id": "h1...", "day_of_week": 0, "opens_at": "08:00:00", "closes_at": "13:00:00" },
    { "id": "h2...", "day_of_week": 0, "opens_at": "16:00:00", "closes_at": "20:00:00" },
    { "id": "h3...", "day_of_week": 1, "opens_at": "08:00:00", "closes_at": "14:00:00" }
  ]
}
```

> `day_of_week` es **Python weekday**: `0`=lunes, `6`=domingo. El frontend rotula con ese mapeo.

#### `PUT /api/v1/clinic/offices/{id}/operating-hours`

**Permiso**: `OFFICE_HOURS_WRITE`. Reemplaza **atómicamente** todo el patrón semanal (no es CRUD por bloque). El cuerpo es la lista completa.

**Request** (`OfficeOperatingHoursReplace`):
```json
{
  "hours": [
    { "day_of_week": 0, "opens_at": "08:00:00", "closes_at": "13:00:00" },
    { "day_of_week": 0, "opens_at": "16:00:00", "closes_at": "20:00:00" },
    { "day_of_week": 1, "opens_at": "08:00:00", "closes_at": "14:00:00" }
  ]
}
```

Para **borrar todo el patrón**, enviar `{ "hours": [] }`.

**Response** `SingleResponse[list[OfficeOperatingHoursItem]]` — el patrón resultante (mismo shape que el GET).

**Error 404** si el office no existe:
```json
{ "success": false, "detail": "Office not found", "code": "OFFICE_NOT_FOUND" }
```

**Error 422** (bloque inválido o solapamiento):
```json
{
  "success": false,
  "detail": "Validation failed",
  "errors": [{ "loc": ["body"], "msg": "overlapping blocks on day_of_week=0 (Python weekday: 0=Mon)", "type": "value_error" }]
}
```

### OfficeClosure (CRUD anidado)

#### `GET /api/v1/clinic/offices/{id}/closures?from=&to=`

**Permiso**: `OFFICE_CLOSURES_READ`. `from`/`to` (ISO 8601) opcionales: filtran por solape de rango. Sin filtros devuelve todas las excepciones no borradas del office.

**Response** `SingleResponse[list[OfficeClosureItem]]`:
```json
{
  "success": true,
  "data": [
    {
      "id": "x1...",
      "office_id": "9f8e...",
      "starts_at": "2026-07-28T00:00:00+00:00",
      "ends_at": "2026-07-29T00:00:00+00:00",
      "is_closed": true,
      "reason": "Feriado 28 de julio",
      "active": true,
      "...": "audit fields"
    }
  ]
}
```

#### `POST /api/v1/clinic/offices/{id}/closures`

**Permiso**: `OFFICE_CLOSURES_WRITE`.

**Request** (`OfficeClosureCreate`):
```json
{
  "starts_at": "2026-07-28T00:00:00-05:00",
  "ends_at": "2026-07-29T00:00:00-05:00",
  "is_closed": true,
  "reason": "Feriado 28 de julio"
}
```

Para una **apertura extra** (abrir un domingo aunque el patrón diga cerrado): `is_closed: false`.

**Response 201** `SingleResponse[OfficeClosureDetail]`.

**Error 422** si `ends_at <= starts_at`:
```json
{
  "success": false,
  "detail": "Validation failed",
  "errors": [{ "loc": ["body"], "msg": "ends_at must be later than starts_at", "type": "value_error" }]
}
```

#### `DELETE /api/v1/clinic/offices/{id}/closures/{closure_id}` → soft-delete

**Permiso**: `OFFICE_CLOSURES_WRITE`. **Response 204**.

**Error 404** si el closure no existe o no pertenece a ese office:
```json
{ "success": false, "detail": "Closure not found", "code": "CLOSURE_NOT_FOUND" }
```

## Lógica importante (decisiones que el código no expresa solo)

### Cómo hidratar `offices_count` / `branch_name` / `verticals_count` / `verticals`

Los `Item` schemas llevan **agregados denormalizados** para evitar joins en el frontend (mismo patrón que `services_count`/`vertical_name` en `catalog`). En el service:

```python
# services/branch.py — list_paginated
async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[BranchItem]:
    items, total = await branch_repository.get_paginated(db, query_request)
    counts = await branch_repository.count_active_offices_map(db, [b.id for b in items])
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(b, audit_users, offices_count=counts.get(b.id, 0)) for b in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )
```

```python
# services/office.py — list_paginated
async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[OfficeItem]:
    items, total = await office_repository.get_paginated(db, query_request)
    # Two batch lookups, no N+1: branch names + apt-vertical counts.
    branch_names = await office_repository.branch_name_map(
        db, [o.branch_id for o in items]
    )
    vcounts = await office_repository.count_apt_verticals_map(db, [o.id for o in items])
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[
                _to_item(
                    o, audit_users,
                    branch_name=branch_names.get(o.branch_id, ""),
                    verticals_count=vcounts.get(o.id, 0),
                )
                for o in items
            ],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )
```

Para `OfficeDetail` (`get_by_id`, post-create, post-update), `office_repository.get_full` ya hace `selectinload(Office.branch)` + `selectinload(Office.verticals)` con el filtro de soft-delete, así que `_to_detail` lee `office.branch` y `office.verticals` sin más queries.

### Filtrar verticales soft-deleted (sin acoplar a `catalog`)

Confirmado: la asociación `office_vertical` apunta a `catalog.vertical.id`. Cuando `catalog` hace soft-delete de una vertical, **las filas `office_vertical` quedan** (no extendemos el delete guard de catalog — eso lo acoplaría). En su lugar, `clinic` **filtra** las verticales muertas en cada lectura:

- En `get_full`: `with_loader_criteria(Vertical, Vertical.deleted_at.is_(None))` aplica el filtro al `selectinload(Office.verticals)`.
- En `count_apt_verticals_map`: join a `vertical` + `WHERE vertical.deleted_at IS NULL`.
- En `list_active(vertical_id=...)`: el EXISTS join exige `vertical.deleted_at IS NULL`.

Resultado: una vertical soft-deleted desaparece de `OfficeDetail.verticals`, del `verticals_count`, y de los filtros, sin que `catalog` sepa que existe `office_vertical`. El FK `RESTRICT` solo actúa como backstop ante un hard-delete.

### Reemplazo atómico del patrón de horarios (bulk PUT)

`PUT /offices/{id}/operating-hours` es un **replace de agregado**, no CRUD por bloque. La lógica:

```python
# services/office_operating_hours.py
async def replace(
    db: AsyncSession,
    office_id: str,
    payload: OfficeOperatingHoursReplace,
    *,
    actor_id: str,
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    office = await office_repository.get_by_id(db, office_id)
    if office is None:
        raise NotFoundException("Office not found", code="OFFICE_NOT_FOUND")

    # 1) Retire the current pattern (soft-delete the live rows — see the repo
    #    method). BaseRepository reads filter deleted_at, so the old blocks
    #    vanish from subsequent reads while staying uniform with the template.
    await office_operating_hours_repository.soft_delete_for_office(db, office_id)

    # 2) Insert the new set. The whole thing runs in ONE request transaction
    #    (get_db commits at the end), so there is never an intermediate state
    #    where "afternoon was deleted before the new one was created" is visible.
    now = utc_now()
    for block in payload.hours:
        db.add(
            OfficeOperatingHours(
                id=generate_uuid(),
                office_id=office_id,
                day_of_week=block.day_of_week,
                opens_at=block.opens_at,
                closes_at=block.closes_at,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
    await db.flush()

    # 3) Return the resulting pattern (re-read, ordered).
    rows = await office_operating_hours_repository.list_for_office(db, office_id)
    return SingleResponse(
        data=[OfficeOperatingHoursItem.model_validate(r, from_attributes=True) for r in rows]
    )
```

**Atomicidad**: todo corre dentro de la transacción del request (`get_db` hace `commit` al final, `rollback` si algo lanza). No hay `commit` intermedio. Si la validación Pydantic (solape, `closes_at > opens_at`) o el CHECK de BD fallan, la transacción entera se revierte y el patrón viejo queda intacto. Trade-off conocido (ver [`README.md`](README.md#decisiones-de-diseño-no-obvias)): no hay traza fina de "qué bloque cambió".

### Soft-delete con children (guard 409 `BRANCH_HAS_ACTIVE_CHILDREN`)

Idéntico al guard de `catalog` (`SERVICE_HAS_ACTIVE_CHILDREN`) pero a nivel `Branch → Office`. `DELETE /branches/{id}` **NO** hace cascade:

```python
# services/branch.py
async def soft_delete(db: AsyncSession, branch_id: str, *, actor_id: str) -> None:
    branch = await branch_repository.get_by_id(db, branch_id)
    if branch is None:
        raise NotFoundException("Branch not found")
    # "Active" here = not soft-deleted (a merely disabled office still holds the
    # FK), so the guard counts every non-deleted office. Deleting them unblocks.
    active_offices = await branch_repository.count_active_offices(db, branch_id)
    if active_offices > 0:
        raise ConflictException(
            f"Cannot delete branch with {active_offices} office(s) still attached. "
            "Delete its offices first.",
            code="BRANCH_HAS_ACTIVE_CHILDREN",
        )
    branch.updated_by = actor_id
    branch.updated_on = utc_now()
    await branch_repository.soft_delete(db, branch)
```

`Office` **no** tiene guard equivalente: sus hijos (`operating_hours`, `closures`) son value aggregates internos del office, no entidades de otros módulos. Borrar un office es válido aunque tenga horarios/closures — quedan colgados pero filtrados por `deleted_at` del office en cualquier lectura de `scheduling`. (Las filas `office_vertical` tampoco bloquean: la M:N no es "children activos".)

### Resolución de la M:N en create / update de Office

Mismo patrón que `_resolve_roles`/`_resolve_permissions` del módulo `admin` (`admin/services/user.py`):

```python
# services/office.py
async def _resolve_verticals(db: AsyncSession, vertical_ids: list[str]):
    if not vertical_ids:
        return []
    # vertical_repository.get_by_ids filters deleted_at IS NULL — a soft-deleted
    # vertical is "unknown" for the purposes of attaching it to an office.
    verticals = await vertical_repository.get_by_ids(db, vertical_ids)
    if len(verticals) != len(set(vertical_ids)):
        found = {v.id for v in verticals}
        missing = sorted(set(vertical_ids) - found)
        raise BadRequestException(f"Unknown vertical(s): {', '.join(missing)}")
    return verticals
```

En `create`: `office.verticals = await _resolve_verticals(db, payload.vertical_ids)` antes del `db.add`. En `update`: solo si `vertical_ids` viene en el payload (`exclude_unset`), se hace `office.verticals = await _resolve_verticals(...)` (reemplazo total). Tras crear/actualizar, **recargar con `get_full`** para rehidratar `branch`/`verticals` (el `db.refresh` del `BaseRepository` expira las relaciones `lazy="raise"` — mismo patrón reload-via-get_full que usa `catalog.service`).

> **Nota**: `vertical_repository.get_by_ids` es un helper análogo a `role_repository.get_by_ids`/`permission_repository.get_by_ids` del template. Si `catalog` aún no lo expone, agregarlo al `VerticalRepository` (un `select(Vertical).where(Vertical.id.in_(ids), Vertical.deleted_at.is_(None))`) en la fase F2 — es un cambio aditivo y desacoplado.

### Inmutabilidad de `code` / `branch_id` y FKs

- `Branch.code` y `Office.code` son **slugs/identificadores estables**. Los `*Update` schemas los **omiten** deliberadamente (los bots y URLs internas los usan).
- `Office.branch_id` **no** es updatable — mover un office de sede cambiaría las coordenadas geográficas/timezone implícitas de sus horarios y rompería la atribución de citas históricas. Si negocio lo pide, se diseña `/move` específico (como en `catalog`).

### `BaseRepository` filtra `deleted_at IS NULL` automáticamente

Igual que en `catalog`: en `get_by_id` / `get_paginated` **no** repetir el filtro. Para queries custom (`get_by_code`, `list_active`, `list_for_office`, los counts), sí hay que agregarlo explícitamente como en los ejemplos.

### Audit columns con `created_by` / `updated_by`

Cada service que persiste recibe `actor_id` explícitamente desde el router (patrón shipped: `actor: CurrentAuth` separado del `dependencies=[Depends(RequirePermission(...))]`):

```python
# routers/branch.py
@router.post(
    "",
    response_model=SingleResponse[BranchDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("BRANCHES_CREATE"))],
)
async def create_branch(
    payload: BranchCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[BranchDetail]:
    return await branch_service.create(db, payload, actor_id=actor.id)
```

El service hace `branch.created_by = actor_id` antes de `db.add`. `updated_by`/`updated_on` se actualizan en cada `update()` / `soft_delete()`.

## Routers — ejemplos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]` en el decorator; `actor: CurrentAuth` aparte cuando se necesita el id para audit; `/active` antes de `/{id}` para que no lo capture la ruta dinámica.

```python
# routers/branch.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.clinic.schemas.branch import (
    BranchCreate,
    BranchDetail,
    BranchItem,
    BranchOption,
    BranchUpdate,
)
from app.modules.clinic.services import branch as branch_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/branches", tags=["clinic · branches"])

BranchIdPath = Annotated[str, Path(min_length=1, description="Branch UUID")]


@router.get(
    "/active",
    response_model=list[BranchOption],
    dependencies=[Depends(RequirePermission("BRANCHES_READ"))],
)
async def list_active_branches(db: DBSession) -> list[BranchOption]:
    return await branch_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[BranchItem],
    dependencies=[Depends(RequirePermission("BRANCHES_READ"))],
)
async def list_branches(query: QueryRequest, db: DBSession) -> PaginatedResponse[BranchItem]:
    return await branch_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[BranchDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("BRANCHES_CREATE"))],
)
async def create_branch(
    payload: BranchCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[BranchDetail]:
    return await branch_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{branch_id}",
    response_model=SingleResponse[BranchDetail],
    dependencies=[Depends(RequirePermission("BRANCHES_READ"))],
)
async def get_branch(branch_id: BranchIdPath, db: DBSession) -> SingleResponse[BranchDetail]:
    return await branch_service.get_by_id(db, branch_id)


@router.put(
    "/{branch_id}",
    response_model=SingleResponse[BranchDetail],
    dependencies=[Depends(RequirePermission("BRANCHES_UPDATE"))],
)
async def update_branch(
    branch_id: BranchIdPath,
    payload: BranchUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[BranchDetail]:
    return await branch_service.update(db, branch_id, payload, actor_id=actor.id)


@router.delete(
    "/{branch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("BRANCHES_DELETE"))],
)
async def delete_branch(branch_id: BranchIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await branch_service.soft_delete(db, branch_id, actor_id=actor.id)
```

`office.py` análogo, con el `/active` filtrable:

```python
# routers/office.py — solo el /active difiere del patrón de branch
@router.get(
    "/active",
    response_model=list[OfficeOption],
    dependencies=[Depends(RequirePermission("OFFICES_READ"))],
)
async def list_active_offices(
    db: DBSession,
    branch_id: str | None = None,
    vertical_id: str | None = None,
) -> list[OfficeOption]:
    return await office_service.list_active(db, branch_id=branch_id, vertical_id=vertical_id)
```

Los routers anidados (`operating_hours`, `closure`) cuelgan de `/offices/{office_id}/...`. Usan el mismo `office_id` como `Path` y validan que el office exista en el service:

```python
# routers/office_operating_hours.py
router = APIRouter(prefix="/offices", tags=["clinic · office hours"])

OfficeIdPath = Annotated[str, Path(min_length=1, description="Office UUID")]


@router.get(
    "/{office_id}/operating-hours",
    response_model=SingleResponse[list[OfficeOperatingHoursItem]],
    dependencies=[Depends(RequirePermission("OFFICE_HOURS_READ"))],
)
async def get_operating_hours(
    office_id: OfficeIdPath, db: DBSession
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    return await office_operating_hours_service.list_for_office(db, office_id)


@router.put(
    "/{office_id}/operating-hours",
    response_model=SingleResponse[list[OfficeOperatingHoursItem]],
    dependencies=[Depends(RequirePermission("OFFICE_HOURS_WRITE"))],
)
async def replace_operating_hours(
    office_id: OfficeIdPath,
    payload: OfficeOperatingHoursReplace,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    return await office_operating_hours_service.replace(db, office_id, payload, actor_id=actor.id)
```

```python
# routers/office_closure.py
router = APIRouter(prefix="/offices", tags=["clinic · office closures"])

OfficeIdPath = Annotated[str, Path(min_length=1, description="Office UUID")]
ClosureIdPath = Annotated[str, Path(min_length=1, description="Closure UUID")]


@router.get(
    "/{office_id}/closures",
    response_model=SingleResponse[list[OfficeClosureItem]],
    dependencies=[Depends(RequirePermission("OFFICE_CLOSURES_READ"))],
)
async def list_closures(
    office_id: OfficeIdPath,
    db: DBSession,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
) -> SingleResponse[list[OfficeClosureItem]]:
    return await office_closure_service.list_for_office(db, office_id, from_, to)


@router.post(
    "/{office_id}/closures",
    response_model=SingleResponse[OfficeClosureDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("OFFICE_CLOSURES_WRITE"))],
)
async def create_closure(
    office_id: OfficeIdPath,
    payload: OfficeClosureCreate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[OfficeClosureDetail]:
    return await office_closure_service.create(db, office_id, payload, actor_id=actor.id)


@router.delete(
    "/{office_id}/closures/{closure_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("OFFICE_CLOSURES_WRITE"))],
)
async def delete_closure(
    office_id: OfficeIdPath,
    closure_id: ClosureIdPath,
    db: DBSession,
    actor: CurrentAuth,
) -> None:
    await office_closure_service.soft_delete(db, office_id, closure_id, actor_id=actor.id)
```

> `from` es palabra reservada en Python; el parámetro se declara `from_` con `Query(alias="from")` para mantener `?from=` en la URL.

## Migration

Migraciones **manuales y numeradas** (convención medisage: `0005..` en adelante, `down_revision` encadenado — `0004` es la última de `catalog`). Ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md#migraciones-alembic). Una migración por entidad, alineada a las fases F1-F4. Las `CheckConstraint` se declaran **tanto en `__table_args__` como en el SQL** de la migración.

### `0005_clinic_branch.py` (F1)

```sql
CREATE TABLE branch (
    id            VARCHAR(36) PRIMARY KEY,
    code          VARCHAR(40) NOT NULL UNIQUE,
    name          VARCHAR(120) NOT NULL,
    address_line  VARCHAR(255) NOT NULL,
    district      VARCHAR(120),
    city          VARCHAR(120) NOT NULL,
    region        VARCHAR(120),
    country       VARCHAR(2) NOT NULL DEFAULT 'PE',
    postal_code   VARCHAR(20),
    latitude      NUMERIC(9,6),
    longitude     NUMERIC(9,6),
    phone         VARCHAR(40),
    email         VARCHAR(255),
    timezone      VARCHAR(60) NOT NULL DEFAULT 'America/Lima',
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at    TIMESTAMPTZ,
    created_on    TIMESTAMPTZ NOT NULL,
    created_by    VARCHAR(36) NOT NULL,
    updated_on    TIMESTAMPTZ NOT NULL,
    updated_by    VARCHAR(36) NOT NULL
);
CREATE INDEX ix_branch_code ON branch (code);
-- down_revision = "0004" (last catalog migration)
```

### `0006_clinic_office.py` (F2 — office + office_vertical M:N)

```sql
CREATE TABLE office (
    id          VARCHAR(36) PRIMARY KEY,
    branch_id   VARCHAR(36) NOT NULL REFERENCES branch(id),  -- RESTRICT
    code        VARCHAR(40) NOT NULL,
    name        VARCHAR(120) NOT NULL,
    room_number VARCHAR(20),
    floor       VARCHAR(20),
    description VARCHAR(500),
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at  TIMESTAMPTZ,
    created_on  TIMESTAMPTZ NOT NULL,
    created_by  VARCHAR(36) NOT NULL,
    updated_on  TIMESTAMPTZ NOT NULL,
    updated_by  VARCHAR(36) NOT NULL,
    CONSTRAINT uq_office_branch_code UNIQUE (branch_id, code)
);
CREATE INDEX ix_office_branch_id ON office (branch_id);

-- M:N office ↔ catalog.vertical
CREATE TABLE office_vertical (
    office_id   VARCHAR(36) NOT NULL REFERENCES office(id)   ON DELETE CASCADE,
    vertical_id VARCHAR(36) NOT NULL REFERENCES vertical(id),  -- RESTRICT backstop
    PRIMARY KEY (office_id, vertical_id)
);
-- down_revision = "0005"
```

### `0007_clinic_office_operating_hours.py` (F3)

```sql
CREATE TABLE office_operating_hours (
    id          VARCHAR(36) PRIMARY KEY,
    office_id   VARCHAR(36) NOT NULL REFERENCES office(id),
    day_of_week SMALLINT NOT NULL,                 -- 0=Mon .. 6=Sun (Python weekday)
    opens_at    TIME WITHOUT TIME ZONE NOT NULL,
    closes_at   TIME WITHOUT TIME ZONE NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at  TIMESTAMPTZ,
    created_on  TIMESTAMPTZ NOT NULL,
    created_by  VARCHAR(36) NOT NULL,
    updated_on  TIMESTAMPTZ NOT NULL,
    updated_by  VARCHAR(36) NOT NULL,
    CONSTRAINT ck_office_hours_closes_after_opens   CHECK (closes_at > opens_at),
    CONSTRAINT ck_office_hours_day_of_week_range    CHECK (day_of_week >= 0 AND day_of_week <= 6)
);
CREATE INDEX ix_office_operating_hours_office_id ON office_operating_hours (office_id);
-- NO unique on (office_id, day_of_week): multiple blocks per day allowed.
-- down_revision = "0006"
```

### `0008_clinic_office_closure.py` (F4)

```sql
CREATE TABLE office_closure (
    id          VARCHAR(36) PRIMARY KEY,
    office_id   VARCHAR(36) NOT NULL REFERENCES office(id),
    starts_at   TIMESTAMPTZ NOT NULL,
    ends_at     TIMESTAMPTZ NOT NULL,
    is_closed   BOOLEAN NOT NULL DEFAULT TRUE,
    reason      VARCHAR(255) NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at  TIMESTAMPTZ,
    created_on  TIMESTAMPTZ NOT NULL,
    created_by  VARCHAR(36) NOT NULL,
    updated_on  TIMESTAMPTZ NOT NULL,
    updated_by  VARCHAR(36) NOT NULL,
    CONSTRAINT ck_office_closure_ends_after_starts CHECK (ends_at > starts_at)
);
CREATE INDEX ix_office_closure_office_id ON office_closure (office_id);
-- down_revision = "0007"
```

**Sin `ON DELETE CASCADE`** en los FKs a `branch`/`office` (salvo `office_vertical.office_id`): `office.branch_id`, `office_operating_hours.office_id`, `office_closure.office_id` y `office_vertical.vertical_id` son `RESTRICT` (default), reforzando los guards de service y el backstop ante hard-deletes.

## Seed

Los **13 permisos** de `clinic` ya están consolidados en [`_seed-and-roles.md`](../_seed-and-roles.md) (`MENU-CLINIC`, `BRANCHES_*`, `OFFICES_*`, `OFFICE_HOURS_READ/WRITE`, `OFFICE_CLOSURES_READ/WRITE`) y asignados a `ADMIN` (todos), `DOCTOR` (los `*_READ`) y `ASESOR` (`MENU-CLINIC` + `BRANCHES_READ` + `OFFICES_READ`). **Nada más que seedear**: branches/offices son datos operativos que el admin de cada clínica configura (igual que catalog no seedea verticals/services/products). No hay catálogos configurables en `clinic`.

## Checklist de implementación (mapeado a fases F0–F4)

### F0 — Prep
- [ ] Agregar los 13 permisos de `clinic` a `app/core/seed.py:SEED_PERMISSIONS` (ya consolidados en [`_seed-and-roles.md`](../_seed-and-roles.md)).
- [ ] Asegurar que `ADMIN`/`DOCTOR`/`ASESOR` reciban el subset documentado.
- [ ] Crear el esqueleto `backend/app/modules/clinic/{models,schemas,repositories,services,routers}/` + `models/associations.py`.
- [ ] Registrar el módulo en `app/modules/__init__.py` (`from app.modules import admin, catalog, clinic`).
- [ ] Incluir el aggregator router en `app/main.py` (`prefix="/clinic"`).
- [ ] (Frontend F0) nav "Clínica" → Sedes, Consultorios + íconos de sidebar (ver [`frontend.md`](frontend.md)).

### F1 — Branch
- [ ] `models/branch.py` + migration `0005_clinic_branch` (`down_revision="0004"`).
- [ ] `schemas/branch.py` (Create/Update/Item/Detail/Option) con validators code-slug, country ISO, timezone IANA.
- [ ] `repositories/branch.py` con `ALLOWED_FIELDS`, `get_by_code`, `list_active`, `count_active_offices(_map)`.
- [ ] `services/branch.py` (módulo de funciones) + `routers/branch.py` (CRUD + `/active`, `PUT` para update).
- [ ] Smoke test: login admin → `POST /clinic/branches/list` body vacío → `200` items vacíos.
- [ ] Test unique: crear branch con `code` duplicado → `409 BRANCH_CODE_TAKEN`.
- [ ] Test validación: `code: "Lima Centro"` (no slug) / `country: "PER"` → `422`.

### F2 — Office + office_vertical M:N
- [ ] `models/associations.py` (`office_vertical`) + `models/office.py` + migration `0006_clinic_office`.
- [ ] Activar `Branch.offices_count` (denormalización) en `BranchItem`.
- [ ] `schemas/office.py` con `vertical_ids` en Create/Update + `branch`/`verticals` en Detail.
- [ ] `repositories/office.py`: `get_by_branch_and_code`, `get_full` (con `with_loader_criteria` filtrando verticales soft-deleted), `list_active(branch_id, vertical_id)`, `count_apt_verticals_map`, `branch_name_map`.
- [ ] `services/office.py`: `_resolve_verticals`, reload-via-`get_full` post create/update.
- [ ] `routers/office.py`: CRUD + `/active?branch_id=&vertical_id=` (lista cruda).
- [ ] Guard 409 `BRANCH_HAS_ACTIVE_CHILDREN` en `branch_service.soft_delete`.
- [ ] (Frontend F2) shell de la página de detalle `/clinic/offices/{id}` con tabs (ver [`ui.md`](ui.md)).
- [ ] Test soft-delete con children: branch → office → `DELETE branch` falla `409`.
- [ ] Test M:N: crear office con `vertical_ids` → `OfficeDetail.verticals` los lista; soft-delete una vertical en catalog → desaparece de `verticals`/`verticals_count`.

### F3 — OfficeOperatingHours (bulk PUT)
- [ ] `models/office_operating_hours.py` (CHECK `closes_at>opens_at` + rango `day_of_week`) + migration `0007`.
- [ ] `schemas/office_operating_hours.py` (`Item` + `Replace`) con validators 0..6, `closes_at>opens_at`, no-overlap.
- [ ] `repositories/office_operating_hours.py`: `list_for_office`, `soft_delete_for_office`.
- [ ] `services/office_operating_hours.py`: `replace` atómico + `list_for_office`.
- [ ] `routers/office_operating_hours.py`: `GET` + `PUT /offices/{id}/operating-hours`.
- [ ] Test bulk replace: `PUT` con 3 bloques → `GET` los devuelve; `PUT {hours:[]}` los borra todos.
- [ ] Test atomicidad: `PUT` con un bloque inválido (solape) → `422` y el patrón previo intacto.

### F4 — OfficeClosure (CRUD anidado)
- [ ] `models/office_closure.py` (CHECK `ends_at>starts_at`) + migration `0008`.
- [ ] `schemas/office_closure.py` (Create/Item/Detail — sin Update; editar = borrar + recrear) con validator `ends_at>starts_at`.
- [ ] `repositories/office_closure.py`: `list_for_office(from, to)` con solape de rango.
- [ ] `services/office_closure.py`: `create`, `list_for_office`, `soft_delete` (valida que el closure pertenezca al office).
- [ ] `routers/office_closure.py`: `GET ?from=&to=`, `POST`, `DELETE` anidados bajo `/offices/{id}/closures`.
- [ ] Test cierre vs apertura extra: `is_closed:true` y `is_closed:false` se persisten y listan.
- [ ] Test validación: `ends_at <= starts_at` → `422`.
- [ ] Test ownership: `DELETE` de un `closure_id` de otro office → `404 CLOSURE_NOT_FOUND`.
