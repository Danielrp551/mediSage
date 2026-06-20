# Módulo `catalog` — Backend deep-dive

> **Última actualización**: 2026-05-28
> **Audiencia**: developer implementando `backend/app/modules/catalog/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview), [`../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template) y [`../../diagrams/er-catalog.puml`](../../diagrams/er-catalog.puml).

## Estructura de archivos a crear

```
backend/app/modules/catalog/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── vertical.py
│   ├── service.py
│   └── product.py
├── schemas/
│   ├── __init__.py
│   ├── vertical.py
│   ├── service.py
│   └── product.py
├── repositories/
│   ├── __init__.py
│   ├── vertical.py
│   ├── service.py
│   └── product.py
├── services/
│   ├── __init__.py
│   ├── vertical.py
│   ├── service.py
│   └── product.py
└── routers/
    ├── __init__.py
    ├── vertical.py
    ├── service.py
    └── product.py
```

**No hay `models/associations.py`** porque catalog no tiene M:N propias. Las M:N que tocan catalog (`office_vertical`, `doctor_vertical`, `promotion_product`) viven en sus módulos respectivos (`clinic`, `staff`, `marketing`) — referencian a `catalog.vertical.id` / `catalog.product.id` pero la asociación es propiedad del otro módulo.

Registrar el módulo en `app/modules/__init__.py`:

```python
from app.modules import admin, catalog  # noqa: F401
```

Y registrar los routers en `app/main.py`:

```python
from app.modules.catalog.routers import (
    product as catalog_product_router,
    service as catalog_service_router,
    vertical as catalog_vertical_router,
)

app.include_router(catalog_vertical_router.router)
app.include_router(catalog_service_router.router)
app.include_router(catalog_product_router.router)
```

## Models — SQLAlchemy 2.0

### `models/vertical.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.service import Service


class Vertical(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "vertical"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(60), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    services: Mapped[list["Service"]] = relationship(
        back_populates="vertical", lazy="raise"
    )
```

### `models/service.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.product import Product
    from app.modules.catalog.models.vertical import Vertical


class Service(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "service"
    __table_args__ = (
        UniqueConstraint("vertical_id", "code", name="uq_service_vertical_code"),
    )

    vertical_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vertical.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    vertical: Mapped["Vertical"] = relationship(back_populates="services", lazy="raise")
    products: Mapped[list["Product"]] = relationship(
        back_populates="service", lazy="raise"
    )
```

### `models/product.py`

```python
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.service import Service


class Product(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("service_id", "code", name="uq_product_service_code"),
    )

    service_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service.id"), nullable=False, index=True
    )
    # Vertical padre denormalizada, copiada del service en el create. FK sin
    # relationship — el path canónico es product -> service -> vertical.
    vertical_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vertical.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PEN")
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_appointment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_package: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_hours_to_cancel: Mapped[int | None] = mapped_column(Integer, nullable=True)

    service: Mapped["Service"] = relationship(back_populates="products", lazy="raise")
```

**Lazy strategy**: todas las relaciones en `lazy="raise"` (default del template para evitar N+1). Cuando un service necesite cargar `service.vertical` o `product.service`, hace `selectinload(...)` explícito en el repo.

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (oficiales FastAPI/Pydantic v2 — ver skill `fastapi`):
>
> 1. **No usar Ellipsis (`...`)** en `Field(...)`. Pydantic v2 ya trata el campo como obligatorio si no tiene `default=`. El template existente (`admin/schemas/user.py`) sí usa Ellipsis — drift conocido, código nuevo de medisage sigue la convención oficial.
> 2. **`Annotated`** se usa para parámetros HTTP (`Query`, `Path`, `Header`) en routers — los campos de Pydantic models siguen el patrón `nombre: tipo = Field(...)`.
> 3. **Validators**: `@field_validator` para single-field, `@model_validator(mode="after")` para cross-field.


### `schemas/vertical.py`

```python
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class VerticalCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=60)
    display_order: int = Field(default=0, ge=0, le=9999)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        # Slug rule: lowercase letters, digits, underscores. Must start with
        # a letter and end with letter/digit. Min 3 chars (regex enforces).
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError(
                "code must be lowercase slug: letters/digits/_, "
                "start with letter, end with letter or digit (3-40 chars)"
            )
        return v

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not HEX_COLOR_PATTERN.fullmatch(v):
            raise ValueError("color must be hex like #RRGGBB")
        return v.upper()


class VerticalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=60)
    display_order: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None
    # NOTE: `code` is intentionally NOT updatable. It's a stable slug used by
    # bots and reports. To "rename" semantically, create a new vertical and
    # migrate manually.

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not HEX_COLOR_PATTERN.fullmatch(v):
            raise ValueError("color must be hex like #RRGGBB")
        return v.upper()


class VerticalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    icon: str | None
    display_order: int
    active: bool
    services_count: int
    products_count: int
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class VerticalDetail(VerticalItem):
    """Same shape as Item for verticals — no extra relations to load."""


class VerticalOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    icon: str | None = None
```

### `schemas/service.py`

```python
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,58}[a-z0-9]$")


class ServiceCreate(BaseModel):
    vertical_id: str
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    display_order: int = Field(default=0, ge=0, le=9999)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError("code must be a lowercase slug (a-z, 0-9, _)")
        return v


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    display_order: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None
    # NOT updatable: vertical_id (would orphan products), code (stable slug).


class ServiceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    vertical_id: str
    vertical_name: str  # denormalized for table rows (avoids drawer fetch)
    code: str
    name: str
    description: str | None
    display_order: int
    active: bool
    products_count: int
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class ServiceDetail(ServiceItem):
    vertical: VerticalOption


class ServiceOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    vertical_id: str
    code: str
    name: str
```

### `schemas/product.py`

```python
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.service import ServiceOption
from app.modules.catalog.schemas.vertical import VerticalOption

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,58}[a-z0-9]$")
ISO_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


class ProductCreate(BaseModel):
    service_id: str
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    base_price: Decimal = Field(ge=Decimal("0"), max_digits=10, decimal_places=2)
    currency: str = Field(default="PEN", max_length=3)
    duration_min: int | None = Field(default=None, ge=1, le=24 * 60)
    requires_appointment: bool = True
    is_package: bool = False
    min_hours_to_cancel: int | None = Field(default=None, ge=0, le=24 * 7)

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError("code must be a lowercase slug (a-z, 0-9, _)")
        return v

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str) -> str:
        if not ISO_CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be ISO 4217 alpha-3 (e.g. PEN, USD)")
        return v

    @model_validator(mode="after")
    def _appointment_implies_duration(self) -> "ProductCreate":
        # If the product is agendable, business needs duration_min so
        # scheduling can compute slots. We accept NULL (treat as
        # doctor.slot_duration_min fallback) but flag the inconsistency
        # `requires_appointment=true + min_hours_to_cancel set + duration NULL`
        # which is almost certainly a data-entry mistake.
        if (
            self.requires_appointment
            and self.min_hours_to_cancel is not None
            and self.duration_min is None
        ):
            raise ValueError(
                "duration_min is required when requires_appointment=true "
                "and min_hours_to_cancel is set"
            )
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    base_price: Decimal | None = Field(
        default=None, ge=Decimal("0"), max_digits=10, decimal_places=2
    )
    currency: str | None = Field(default=None, max_length=3)
    duration_min: int | None = Field(default=None, ge=1, le=24 * 60)
    requires_appointment: bool | None = None
    is_package: bool | None = None
    min_hours_to_cancel: int | None = Field(default=None, ge=0, le=24 * 7)
    active: bool | None = None
    # NOT updatable: service_id (would orphan), code (stable slug).

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not ISO_CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be ISO 4217 alpha-3")
        return v


class ProductItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str
    service_name: str        # denormalized
    vertical_id: str         # denormalized
    vertical_name: str       # denormalized
    code: str
    name: str
    description: str | None
    base_price: Decimal
    currency: str
    duration_min: int | None
    requires_appointment: bool
    is_package: bool
    min_hours_to_cancel: int | None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class ProductDetail(ProductItem):
    service: ServiceOption
    vertical: VerticalOption


class ProductOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str
    code: str
    name: str
    base_price: Decimal
    currency: str
    duration_min: int | None
```

## Repositories

`ALLOWED_FIELDS` es el whitelist de columnas filtrable / ordenable desde el frontend (ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md#queryrequest-y-baserepositoryget_paginated)).

```python
# repositories/vertical.py
class VerticalRepository(BaseRepository[Vertical]):
    ALLOWED_FIELDS = {"code", "name", "active", "display_order", "created_on", "updated_on"}

    def __init__(self) -> None:
        super().__init__(Vertical)

    async def get_by_code(self, db: AsyncSession, code: str) -> Vertical | None:
        result = await db.execute(
            select(Vertical).where(Vertical.code == code, Vertical.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Vertical]:
        result = await db.execute(
            select(Vertical)
            .where(Vertical.active.is_(True), Vertical.deleted_at.is_(None))
            .order_by(Vertical.display_order.asc(), Vertical.name.asc())
        )
        return list(result.scalars().all())

    async def count_active_services(self, db: AsyncSession, vertical_id: str) -> int:
        result = await db.execute(
            select(func.count(Service.id)).where(
                Service.vertical_id == vertical_id,
                Service.deleted_at.is_(None),
            )
        )
        return result.scalar_one()


# repositories/service.py
class ServiceRepository(BaseRepository[Service]):
    ALLOWED_FIELDS = {
        "vertical_id", "code", "name", "active",
        "display_order", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Service)

    async def get_by_vertical_and_code(
        self, db: AsyncSession, vertical_id: str, code: str
    ) -> Service | None:
        result = await db.execute(
            select(Service).where(
                Service.vertical_id == vertical_id,
                Service.code == code,
                Service.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, service_id: str) -> Service | None:
        return await self.get_by_id(db, service_id, load=(selectinload(Service.vertical),))

    async def list_active(
        self, db: AsyncSession, vertical_id: str | None = None
    ) -> list[Service]:
        # Sin eager-load: el único consumidor mapea a ServiceOption, que nunca
        # toca `service.vertical`. Cargarlo aquí sería un SELECT batched inútil.
        stmt = (
            select(Service)
            .where(Service.active.is_(True), Service.deleted_at.is_(None))
            .order_by(Service.display_order.asc(), Service.name.asc())
        )
        if vertical_id is not None:
            stmt = stmt.where(Service.vertical_id == vertical_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())


# repositories/product.py
class ProductRepository(BaseRepository[Product]):
    # `vertical_id` (denormalizado) está en el whitelist para que la página de
    # Products pueda filtrar por vertical sin un join.
    ALLOWED_FIELDS = {
        "service_id", "vertical_id", "code", "name", "active",
        "base_price", "currency", "duration_min",
        "requires_appointment", "is_package",
        "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Product)

    async def get_by_service_and_code(
        self, db: AsyncSession, service_id: str, code: str
    ) -> Product | None:
        result = await db.execute(
            select(Product).where(
                Product.service_id == service_id,
                Product.code == code,
                Product.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, product_id: str) -> Product | None:
        return await self.get_by_id(
            db,
            product_id,
            load=(
                selectinload(Product.service).selectinload(Service.vertical),
            ),
        )

    async def list_active(
        self, db: AsyncSession, service_id: str | None = None
    ) -> list[Product]:
        # Sin eager-load: el único consumidor mapea a ProductOption, que solo
        # lee columnas (nunca las relaciones service/vertical).
        stmt = (
            select(Product)
            .where(Product.active.is_(True), Product.deleted_at.is_(None))
            .order_by(Product.name.asc())
        )
        if service_id is not None:
            stmt = stmt.where(Product.service_id == service_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())
```

## API contracts

Todos los endpoints usan los envelopes del template:
- **Single**: `{ "success": true, "data": <T> }`
- **Paginated**: `{ "success": true, "data": { "items": [...], "total": N, "skip": 0, "limit": 10 } }`
- **Error**: `{ "success": false, "detail": "...", "code"?: "...", "errors"?: [...] }`

### Vertical

#### `POST /api/v1/catalog/verticals/list`

**Request** (`QueryRequest`):
```json
{
  "pagination": { "skip": 0, "limit": 10 },
  "sorting":    { "sort_by": "display_order", "sort_order": "asc" },
  "filters": {
    "filters": [
      { "operator": "AND", "conditions": [
        { "field": "name", "operator": "contains", "value": "estet" },
        { "field": "active", "operator": "eq", "value": true }
      ] }
    ]
  }
}
```

**Response** (`PaginatedResponse[VerticalItem]`):
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "8c5a...",
        "code": "estetica_facial",
        "name": "Estética facial",
        "description": "Tratamientos faciales no invasivos.",
        "color": "#FF6B6B",
        "icon": "Sparkle24Regular",
        "display_order": 10,
        "active": true,
        "services_count": 5,
        "products_count": 14,
        "created_on": "2026-05-28T14:23:10+00:00",
        "created_by": "00000000-0000-0000-0000-000000000001",
        "created_by_user": { "id": "...", "full_name": "Admin User", "email": "admin@..." },
        "updated_on": "2026-05-28T14:23:10+00:00",
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

#### `POST /api/v1/catalog/verticals`

**Request** (`VerticalCreate`):
```json
{
  "code": "estetica_facial",
  "name": "Estética facial",
  "description": "Tratamientos faciales no invasivos.",
  "color": "#FF6B6B",
  "icon": "Sparkle24Regular",
  "display_order": 10
}
```

**Response** `201`:
```json
{ "success": true, "data": { "id": "8c5a...", "code": "estetica_facial", ... } }
```

**Error 409** (code duplicado):
```json
{ "success": false, "detail": "Vertical with code 'estetica_facial' already exists", "code": "VERTICAL_CODE_TAKEN" }
```

#### `GET /api/v1/catalog/verticals/{id}` → `SingleResponse[VerticalDetail]`

#### `PUT /api/v1/catalog/verticals/{id}`

**Request**: cualquier subset de `VerticalUpdate`. `code` no es actualizable (omitir o el server lo ignora).

#### `DELETE /api/v1/catalog/verticals/{id}` → soft-delete

**Response 204** sin body.

**Error 409** si hay servicios activos asociados:
```json
{
  "success": false,
  "detail": "Cannot delete vertical with 3 service(s) still attached. Delete its services first.",
  "code": "VERTICAL_HAS_ACTIVE_CHILDREN"
}
```

#### `GET /api/v1/catalog/verticals/active`

**Response**: `list[VerticalOption]` — lista plana **sin** envelope `{success, data}` (igual que `admin.roles.active`). El frontend lee el array directamente.
```json
[
  { "id": "8c5a...", "code": "estetica_facial", "name": "Estética facial", "color": "#FF6B6B", "icon": "Sparkle24Regular" },
  { "id": "9d6b...", "code": "dental", "name": "Dental", "color": "#3B82F6", "icon": "ToothRegular" }
]
```

### Service

#### `POST /api/v1/catalog/services/list`

**Filtros típicos**:
```json
{
  "pagination": { "skip": 0, "limit": 10 },
  "sorting": { "sort_by": "display_order", "sort_order": "asc" },
  "filters": {
    "filters": [
      { "operator": "AND", "conditions": [
        { "field": "vertical_id", "operator": "eq", "value": "8c5a..." }
      ] }
    ]
  }
}
```

**Response**: items con `vertical_name` denormalizado para evitar joins en el frontend.

#### `POST /api/v1/catalog/services`

**Request** (`ServiceCreate`):
```json
{
  "vertical_id": "8c5a...",
  "code": "limpieza_profunda",
  "name": "Limpieza profunda",
  "description": "Limpieza facial profunda con extracción.",
  "display_order": 10
}
```

**Error 404** si `vertical_id` no existe:
```json
{ "success": false, "detail": "Vertical not found", "code": "VERTICAL_NOT_FOUND" }
```

**Error 409** si `(vertical_id, code)` ya existe:
```json
{
  "success": false,
  "detail": "Service with code 'limpieza_profunda' already exists in this vertical",
  "code": "SERVICE_CODE_TAKEN"
}
```

#### `DELETE /api/v1/catalog/services/{id}`

**Error 409** si hay productos activos:
```json
{ "success": false, "detail": "Cannot delete service with 4 product(s) still attached. Delete its products first.", "code": "SERVICE_HAS_ACTIVE_CHILDREN" }
```

#### `GET /api/v1/catalog/services/active?vertical_id=...`

`vertical_id` es opcional. Sin filtro devuelve todos los servicios activos de todas las verticales (ordenados por vertical → service).

### Product

#### `POST /api/v1/catalog/products`

**Request** (`ProductCreate`):
```json
{
  "service_id": "5e8f...",
  "code": "hydrafacial_premium_60",
  "name": "HydraFacial Premium 60 min",
  "description": "Tratamiento completo con sérum personalizado.",
  "base_price": "350.00",
  "currency": "PEN",
  "duration_min": 60,
  "requires_appointment": true,
  "is_package": false,
  "min_hours_to_cancel": 24
}
```

**Error 422** (validación cross-field):
```json
{
  "success": false,
  "detail": "duration_min is required when requires_appointment=true and min_hours_to_cancel is set",
  "errors": [{ "loc": ["body"], "msg": "...", "type": "value_error" }]
}
```

#### `GET /api/v1/catalog/products/{id}` → `SingleResponse[ProductDetail]`

Incluye `service` y `vertical` resueltos como `Option`:
```json
{
  "success": true,
  "data": {
    "id": "...",
    "service_id": "5e8f...",
    "service_name": "Limpieza profunda",
    "service": { "id": "5e8f...", "vertical_id": "8c5a...", "code": "limpieza_profunda", "name": "Limpieza profunda" },
    "vertical_id": "8c5a...",
    "vertical_name": "Estética facial",
    "vertical": { "id": "8c5a...", "code": "estetica_facial", "name": "Estética facial", "color": "#FF6B6B", "icon": "Sparkle24Regular" },
    "code": "hydrafacial_premium_60",
    "name": "HydraFacial Premium 60 min",
    "base_price": "350.00",
    "currency": "PEN",
    "duration_min": 60,
    "requires_appointment": true,
    "is_package": false,
    "min_hours_to_cancel": 24,
    "active": true,
    "...": "audit fields"
  }
}
```

## Lógica importante (decisiones que el código no expresa solo)

### Cómo hidratar `services_count` / `products_count` / `vertical_name` / `service_name`

Los `Item` schemas llevan **agregados denormalizados** para evitar joins en el frontend. La forma de calcularlos en el service:

```python
# services/vertical.py — list_paginated
async def list_paginated(db: AsyncSession, query: QueryRequest) -> PaginatedResponse[VerticalItem]:
    rows, total = await vertical_repository.get_paginated(db, query)

    # Batch counts: 1 query, no N+1
    ids = [r.id for r in rows]
    if ids:
        counts = await db.execute(
            select(
                Service.vertical_id,
                func.count(Service.id.distinct()).label("services_count"),
                func.count(Product.id.distinct()).label("products_count"),
            )
            .outerjoin(Product, and_(
                Product.service_id == Service.id,
                Product.deleted_at.is_(None),
            ))
            .where(
                Service.vertical_id.in_(ids),
                Service.deleted_at.is_(None),
            )
            .group_by(Service.vertical_id)
        )
        counts_map = {r.vertical_id: (r.services_count, r.products_count) for r in counts}
    else:
        counts_map = {}

    # Audit users
    actor_ids = _collect_actor_ids(rows)
    audit_users = await user_repository.get_audit_info_map(db, actor_ids)

    items = [_to_item(r, counts_map.get(r.id, (0, 0)), audit_users) for r in rows]
    return PaginatedResponse(data=PaginatedData(items=items, total=total, ...))


def _to_item(
    row: Vertical,
    counts: tuple[int, int],
    audit_users: dict[str, User],
) -> VerticalItem:
    services_count, products_count = counts
    return VerticalItem(
        id=row.id,
        code=row.code,
        name=row.name,
        # ... resto de campos
        services_count=services_count,
        products_count=products_count,
        created_by_user=audit_users.get(row.created_by) and UserAuditInfo.model_validate(...),
        updated_by_user=audit_users.get(row.updated_by) and UserAuditInfo.model_validate(...),
    )
```

Para `service.products_count` y `service.vertical_name`: similar, batch lookup. Para `product.service_name` / `product.vertical_name`: el `selectinload(Product.service).selectinload(Service.vertical)` ya carga ambos en el listado paginado (`list_paginated`) y en `get_full`. Los endpoints `/active` **no** eager-loadean: mapean a `ProductOption` / `ServiceOption`, que solo leen columnas y nunca tocan la relación.

### Soft delete con children

`DELETE /verticals/{id}` **NO** hace cascade. Si hay `service` vivos (no soft-deleted, `deleted_at IS NULL` — un servicio meramente deshabilitado sigue conservando el FK) asociados, el service lanza `ConflictException(code="VERTICAL_HAS_ACTIVE_CHILDREN")` (HTTP 409) con conteo:

```python
async def soft_delete(db: AsyncSession, vertical_id: str, *, actor_id: str) -> None:
    vertical = await vertical_repository.get_by_id(db, vertical_id)
    if vertical is None:
        raise NotFoundException("Vertical not found")
    child_services = await vertical_repository.count_active_services(db, vertical_id)
    if child_services > 0:
        raise ConflictException(
            f"Cannot delete vertical with {child_services} service(s) still attached. "
            "Delete its services first.",
            code="VERTICAL_HAS_ACTIVE_CHILDREN",
        )
    vertical.updated_by = actor_id
    vertical.updated_on = utc_now()
    await vertical_repository.soft_delete(db, vertical)
```

Para `service` la misma regla con `products`.

Para `product` no hay regla equivalente porque sus dependencias viven en otros módulos (`appointment`, `promotion_product`). El soft-delete del producto **sí** se permite incluso si tiene citas históricas — esas mantienen el FK, simplemente el producto deja de ser agendable. Si en el futuro queremos bloquear, se valida en `scheduling.appointment.create` que el producto no esté soft-deleted (filtro automático del `BaseRepository`).

### Inmutabilidad del `code` y FKs

- `Vertical.code`, `Service.code`, `Product.code` son **slugs estables**. Los `*Update` schemas **omiten `code`** deliberadamente — los bots lo usan para clasificar leads ("la persona quiere algo de `estetica_facial`"). Cambiar el slug rompe esa atribución.
- `Service.vertical_id` y `Product.service_id` tampoco son updatable — moverían las entidades de "padre", lo que requiere coordinación con `appointment` y `promotion_product`. Si negocio lo pide en el futuro, se diseña un endpoint `/move` específico.

### Validación de `display_order` y orden de listado

`display_order` no es UNIQUE — múltiples verticales pueden tener `display_order=10`. El orden de listado es `ORDER BY display_order ASC, name ASC` para tiebreak determinista. Si admin necesita reordenar, lo hace editando el `display_order` de las filas afectadas.

### `BaseRepository` filtra `deleted_at IS NULL` automáticamente

Por lo tanto en repos custom **NO repetir** `.where(Vertical.deleted_at.is_(None))` cuando uses `get_by_id` o `get_paginated`. Para queries custom (como `get_by_code`), sí hay que agregarlo explícitamente como en los ejemplos arriba.

### Audit columns con `created_by` / `updated_by`

Cada service que persiste recibe `actor_id` explícitamente desde el router:

```python
# routers/vertical.py
@router.post("", status_code=201)
async def create_vertical(
    payload: VerticalCreate,
    db: DBSession,
    auth: CurrentAuth,
    _perm = Depends(RequirePermission("VERTICALS_CREATE")),
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.create(db, payload, auth.user.id)
```

El service hace `vertical.created_by = actor_id` antes de `db.add(vertical)`. `updated_by` se actualiza en cada `update()` / `soft_delete()`.

## Migration

`alembic revision --autogenerate -m "add catalog tables"`. **Revisar el script generado** (alembic no detecta cambios de tipo ni renombrados, ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md#migraciones-alembic)). El upgrade debe incluir:

```sql
-- vertical
CREATE TABLE vertical (
    id           VARCHAR(36) PRIMARY KEY,
    code         VARCHAR(40) NOT NULL UNIQUE,
    name         VARCHAR(120) NOT NULL,
    description  VARCHAR(500),
    color        VARCHAR(20),
    icon         VARCHAR(60),
    display_order INTEGER NOT NULL DEFAULT 0,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at   TIMESTAMPTZ,
    created_on   TIMESTAMPTZ NOT NULL,
    created_by   VARCHAR(36) NOT NULL,
    updated_on   TIMESTAMPTZ NOT NULL,
    updated_by   VARCHAR(36) NOT NULL
);
CREATE INDEX ix_vertical_code ON vertical (code);

-- service
CREATE TABLE service (
    id            VARCHAR(36) PRIMARY KEY,
    vertical_id   VARCHAR(36) NOT NULL REFERENCES vertical(id),
    code          VARCHAR(60) NOT NULL,
    name          VARCHAR(120) NOT NULL,
    description   VARCHAR(500),
    display_order INTEGER NOT NULL DEFAULT 0,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at    TIMESTAMPTZ,
    created_on    TIMESTAMPTZ NOT NULL,
    created_by    VARCHAR(36) NOT NULL,
    updated_on    TIMESTAMPTZ NOT NULL,
    updated_by    VARCHAR(36) NOT NULL,
    CONSTRAINT uq_service_vertical_code UNIQUE (vertical_id, code)
);
CREATE INDEX ix_service_vertical_id ON service (vertical_id);

-- product
CREATE TABLE product (
    id                    VARCHAR(36) PRIMARY KEY,
    service_id            VARCHAR(36) NOT NULL REFERENCES service(id),
    vertical_id           VARCHAR(36) NOT NULL REFERENCES vertical(id),  -- denormalizado del service padre
    code                  VARCHAR(60) NOT NULL,
    name                  VARCHAR(160) NOT NULL,
    description           VARCHAR(1000),
    base_price            NUMERIC(10,2) NOT NULL,
    currency              VARCHAR(3) NOT NULL DEFAULT 'PEN',
    duration_min          INTEGER,
    requires_appointment  BOOLEAN NOT NULL DEFAULT TRUE,
    is_package            BOOLEAN NOT NULL DEFAULT FALSE,
    min_hours_to_cancel   INTEGER,
    active                BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at            TIMESTAMPTZ,
    created_on            TIMESTAMPTZ NOT NULL,
    created_by            VARCHAR(36) NOT NULL,
    updated_on            TIMESTAMPTZ NOT NULL,
    updated_by            VARCHAR(36) NOT NULL,
    CONSTRAINT uq_product_service_code UNIQUE (service_id, code)
);
CREATE INDEX ix_product_service_id ON product (service_id);
CREATE INDEX ix_product_vertical_id ON product (vertical_id);
```

**Sin `ON DELETE CASCADE`** en FKs: `service.vertical_id`, `product.service_id` y `product.vertical_id` son `RESTRICT` (default), reforzando la regla de service "no borrar padre con hijos activos".

## Seed

Solo agregar los 13 permisos a `SEED_PERMISSIONS` (ver [`_seed-and-roles.md`](../_seed-and-roles.md)). **No** se seedean verticales/services/products iniciales — son datos operativos que el admin de cada clínica configura. Esto difiere de los `LeadStatus` / `CustomerStatus` / `AppointmentStatus` que sí se seedean porque son flujos de negocio universales.

## Routers — ejemplo

```python
# routers/vertical.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.catalog.schemas.vertical import (
    VerticalCreate,
    VerticalDetail,
    VerticalItem,
    VerticalOption,
    VerticalUpdate,
)
from app.modules.catalog.services import vertical as vertical_service
from app.shared.base_schemas import (
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)

router = APIRouter(prefix="/api/v1/catalog/verticals", tags=["catalog"])


@router.post("/list", response_model=PaginatedResponse[VerticalItem])
async def list_verticals(
    query: QueryRequest,
    db: DBSession,
    _perm = Depends(RequirePermission("VERTICALS_READ")),
) -> PaginatedResponse[VerticalItem]:
    return await vertical_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[VerticalDetail],
    status_code=status.HTTP_201_CREATED,
)
async def create_vertical(
    payload: VerticalCreate,
    db: DBSession,
    auth: CurrentAuth,
    _perm = Depends(RequirePermission("VERTICALS_CREATE")),
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.create(db, payload, auth.user.id)


@router.get("/active", response_model=list[VerticalOption])
async def list_active_verticals(
    db: DBSession,
    _perm = Depends(RequirePermission("VERTICALS_READ")),
) -> list[VerticalOption]:
    return await vertical_service.list_active(db)


VerticalIdPath = Annotated[str, Path(description="UUID of the vertical")]


@router.get("/{vertical_id}", response_model=SingleResponse[VerticalDetail])
async def get_vertical(
    vertical_id: VerticalIdPath,
    db: DBSession,
    _perm = Depends(RequirePermission("VERTICALS_READ")),
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.get_by_id(db, vertical_id)


@router.put("/{vertical_id}", response_model=SingleResponse[VerticalDetail])
async def update_vertical(
    vertical_id: VerticalIdPath,
    payload: VerticalUpdate,
    db: DBSession,
    auth: CurrentAuth,
    _perm = Depends(RequirePermission("VERTICALS_UPDATE")),
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.update(db, vertical_id, payload, auth.user.id)


@router.delete("/{vertical_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vertical(
    vertical_id: VerticalIdPath,
    db: DBSession,
    auth: CurrentAuth,
    _perm = Depends(RequirePermission("VERTICALS_DELETE")),
) -> None:
    await vertical_service.soft_delete(db, vertical_id, auth.user.id)
```

Análogos para `service` y `product`. `service` y `product` agregan el query param para el endpoint `/active`:

```python
@router.get("/active", response_model=list[ServiceOption])
async def list_active_services(
    db: DBSession,
    vertical_id: str | None = None,
    _perm = Depends(RequirePermission("SERVICES_READ")),
) -> list[ServiceOption]:
    return await service_service.list_active(db, vertical_id=vertical_id)
```

## Checklist de implementación

- [ ] Crear archivos en `backend/app/modules/catalog/` con la estructura listada arriba.
- [ ] Registrar el módulo en `app/modules/__init__.py` (`from app.modules import admin, catalog`).
- [ ] Incluir routers en `app/main.py`.
- [ ] Generar migration `alembic revision --autogenerate -m "add catalog tables"` y revisar el SQL.
- [ ] Agregar los 13 permisos a `app/core/seed.py:SEED_PERMISSIONS`.
- [ ] Asegurar que `ADMIN`, `DOCTOR`, `ASESOR` reciban los permisos según [`_seed-and-roles.md`](../_seed-and-roles.md).
- [ ] Smoke test: login con admin → POST `/api/v1/catalog/verticals/list` con body vacío devuelve `200` con items vacíos.
- [ ] Test de soft-delete con children: crear vertical → crear service → DELETE vertical debe fallar `409`.
- [ ] Test de unique constraints: crear vertical con code duplicado debe fallar `409`.
- [ ] Test de validación: POST vertical con `code: "Estetica Facial"` (no slug) debe fallar `422`.
- [ ] Test de audit columns: crear vertical y verificar que `created_by` apunta al user logueado y `created_by_user` se hidrata.
