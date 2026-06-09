# Módulo `marketing` — Backend deep-dive

> **Última actualización**: 2026-06-08
> **Audiencia**: developer implementando `backend/app/modules/marketing/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`ADR-009`](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (FKs forward a módulos futuros — **marketing es el módulo que las CIERRA**), [`_seed-and-roles.md`](../_seed-and-roles.md) (los 12 permisos `MARKETING` + los 6 ya forward-declarados por `ASESOR` + el user/role `SYSTEM`) y los deep-dives molde [`../crm/backend.md`](../crm/backend.md) (catálogo `code` UNIQUE + denormalización batch sin N+1 + estados con flags) y [`../scheduling/backend.md`](../scheduling/backend.md) (matriz de transición hardcodeada, `apply` atómico cross-módulo, migraciones manuales, bot facade/tools).

> **Contrato autoritativo**: este doc respeta la spec compartida de `marketing` (entidades, campos, endpoints, permisos, códigos de error, fases). Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc. El overview viejo plano `docs/modules/marketing.md` (2026-05-28, idealizado, usaba `PATCH`/`/options`) queda **deprecado** y se consolida en [`README.md`](README.md).

> **Convenciones heredadas de `catalog`/`clinic`/`staff`/`crm`/`conversations`/`bots`/`scheduling` shipped** (repetidas aquí para que el doc se lea solo):
>
> 1. **`PUT` para updates completos** (no `PATCH`). El overview viejo usaba `PATCH` — **deprecado**, reemplazado por `PUT` en TODA la ficha.
> 2. **`/active` para dropdowns**: devuelve **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`), igual que `catalog`/`crm`/`scheduling`. El doc viejo decía `/campaigns/options` → se reconcilia a **`/campaigns/active`**.
> 3. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `AlreadyExistsException`, `ConflictException`, `BadRequestException`, `ForbiddenException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; reload-via-`get_full`/`get_by_id` tras create/update (relaciones `lazy="raise"`); `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` como whitelist estricta (los campos denormalizados NO son server-sortable/filterable — **lección hotfix `cd10c78` de `staff`**).
> 4. **Mensajes `detail` de dominio en español, `code` en inglés**; mensajes de validators Pydantic en inglés (el front re-valida con Zod). UI 100% español.
> 5. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), lista cruda en `/active`, error `{success:false, detail, code?, errors?}`.
> 6. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `marketing` arranca en `0022` (última aplicada antes = `0021_scheduling_appointment`).
> 7. Patrón **audit users**: `created_by`/`updated_by` explícitos; `*_user: UserAuditInfo | None` hidratado vía `user_repository.get_audit_info_map` batch (sin N+1).
> 8. **Decimal en el wire = string**: `Numeric(10,2)` en el modelo, `Decimal` en Pydantic, **serializa como STRING** en el JSON (TS lo tipa `string`). Aritmética SIEMPRE en `Decimal` (nunca float), `ROUND_HALF_UP` a 2 decimales, descuento **cap a base_price** (un descuento nunca supera el precio).

`marketing` es el **módulo #8 (ÚLTIMO)** de medisage: modela las **campañas** (`Campaign`), las **promociones** con descuento discriminado (`Promotion`) y el **registro inmutable de usos** (`PromotionUsage`, audit). Cierra el flujo de negocio **lead → campaña → promo → cita con descuento → cliente**. Depende de módulos YA en prod: `catalog` (`Product.base_price`/`Product.currency`, `Vertical`), `crm` (`Person`), `scheduling` (`Appointment`, integración F4), `admin` (`User` audit). Lo consume `bots` (tool `list_eligible_promotions`, F4) y `scheduling` (auto-wire atómico de `apply_promotion_id`, F4).

**`marketing` es además el módulo que CIERRA ADR-009**: las 3 FKs forward que `crm`/`conversations` dejaron sin constraint (`person_lead_status.source_campaign_id`, `lead_status_history.source_campaign_id`, `channel_account.default_campaign_id`) se cierran con un `ALTER TABLE ADD CONSTRAINT` aditivo en la migración `0022` (la tabla `campaign` ya existe). **No** modifica el código de `crm`/`conversations` (solo el ALTER en la migración).

## Estructura de archivos a crear

```
backend/app/modules/marketing/
├── __init__.py
├── enums.py                          # CampaignStatus (draft|active|paused|ended) + DiscountType (percentage|fixed_amount)
├── models/
│   ├── __init__.py                   # importa todos los modelos (registro en Base.metadata)
│   ├── campaign.py
│   ├── promotion.py
│   ├── promotion_usage.py
│   └── associations.py               # campaign_promotion + promotion_product (M:N)
├── schemas/
│   ├── __init__.py
│   ├── campaign.py                   # Campaign* (Option/Item/Detail/Create/Update) + Transition/PromotionsReplace
│   ├── promotion.py                  # Promotion* (Option/Item/Detail/Create/Update) + ProductsReplace
│   └── promotion_usage.py            # PromotionUsage* + Apply/Eligibility/ComputePrice/Summary
├── repositories/
│   ├── __init__.py
│   ├── campaign.py                   # get_by_code, list_active, get_by_ids, campaign_name_map
│   ├── promotion.py                  # get_by_code, list_active, get_by_ids, get_for_update, promotion_name_map
│   ├── campaign_promotion.py         # M:N campaign_promotion (set/list/count)
│   ├── promotion_product.py          # M:N promotion_product (set/list/count/covers_product, join propio a Product)
│   └── promotion_usage.py            # get_by_appointment, count_for_promotion[_person], usage_summary
├── services/
│   ├── __init__.py
│   ├── campaign.py                   # CRUD + transition (matriz hardcodeada) + M:N promotions
│   ├── promotion.py                  # CRUD + _validate_discount + M:N products + usage_summary
│   └── promotion_usage.py            # apply (10 pasos) + eligible_for/validate/compute_price + _compute_discount + list
└── routers/
    ├── __init__.py                   # aggregator: prefix="/marketing"
    ├── campaign.py                   # /campaigns/* (CRUD + /active + transition + M:N promotions)
    ├── promotion.py                  # /promotions/* (CRUD + /active + M:N products + usage-summary)
    └── promotion_usage.py            # /promotions/eligible-for, /promotions/{id}/validate, /compute-price, /promotion-usages[/list]
```

**Sí hay `models/associations.py`**: `marketing` introduce DOS M:N (`campaign_promotion`, `promotion_product`) como `Table()` puras (PK compuesta, FK `CASCADE`), igual que `staff`/`clinic`. **No** hay tabla de transición de estado (`Campaign.status` es un enum FIJO validado en el service, NO un catálogo configurable ni una matriz `*_transition` — diverge de `crm`/`scheduling`; razón: 4 estados inherentes al ciclo de vida que la clínica no reconfigura, decisión #2).

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean) — **en F1**:

```python
from app.modules import (  # noqa: F401
    admin, bots, catalog, clinic, conversations, crm, marketing, scheduling, staff,
)

__all__ = [
    "admin", "bots", "catalog", "clinic", "conversations", "crm",
    "marketing", "scheduling", "staff",
]
```

Y registrar el aggregator en `app/main.py` (un solo `include_router`, como `crm`/`scheduling`):

```python
from app.modules.marketing.routers import router as marketing_router

app.include_router(marketing_router, prefix=settings.API_V1_PREFIX)  # prefix "/api/v1" + "/marketing" interno
```

El aggregator `routers/__init__.py` replica el patrón de `scheduling/routers/__init__.py`:

```python
"""
Aggregates the marketing sub-routers under one prefix. `main.py` includes este
`router` una vez. El orden importa solo dentro de cada sub-router (/active antes
de /{id}; eligible-for/validate literales antes de /{id}/...); el orden del
aggregator es informativo.
"""

from fastapi import APIRouter

from app.modules.marketing.routers.campaign import router as campaign_router
from app.modules.marketing.routers.promotion import router as promotion_router
from app.modules.marketing.routers.promotion_usage import router as promotion_usage_router

router = APIRouter(prefix="/marketing")
router.include_router(campaign_router)          # /campaigns/* (CRUD + /active + transition + M:N promotions)
router.include_router(promotion_router)         # /promotions/* (CRUD + /active + M:N products + usage-summary)
router.include_router(promotion_usage_router)   # /promotions/eligible-for, /{id}/validate, /compute-price, /promotion-usages

__all__ = ["router"]
```

> ⚠ El `promotion_usage_router` también cuelga de `/promotions/...` (`/promotions/eligible-for`, `/promotions/{id}/validate`). Para que `eligible-for` no lo capture la ruta dinámica `/{id}/products`/`/{id}/validate`, el path literal `/promotions/eligible-for` se declara **antes** de cualquier `/promotions/{id}/...` dentro del router (o se vive el orden de inclusión: `promotion_router` con sus `/{id}/products`/`/{id}/usage-summary` y `promotion_usage_router` con `/eligible-for` + `/{id}/validate`). Como `eligible-for` no colisiona con un UUID, es seguro; `/{id}/validate` cuelga de `/{id}/...` con un segmento literal extra (también seguro). El reparto de endpoints entre `promotion.py` y `promotion_usage.py` se agrupa **por permiso** (ver §Endpoints).

## Enums — `enums.py` (en código, NO en BD)

`CampaignStatus` y `DiscountType` son contratos estables del código (no catálogos en BD). Las columnas que los referencian son `varchar(20)` planas; Pydantic valida contra el enum, la BD almacena el slug.

```python
"""
Marketing enums (code-level value sets, NO DB catalogs).
- CampaignStatus: ciclo de vida FIJO de una campaña (draft→active→paused/ended).
  Persistido como varchar(20). Las transiciones se validan en el SERVICE contra
  una matriz HARDCODEADA (NO una tabla *_transition configurable — diverge de
  crm/scheduling; decisión #2: 4 estados inherentes que la clínica no reconfigura).
- DiscountType: cómo se calcula el descuento de una promoción. INMUTABLE post-create
  (no se puede cambiar percentage↔fixed_amount). Persistido como varchar(20).
"""

from __future__ import annotations

from enum import StrEnum


class CampaignStatus(StrEnum):
    draft = "draft"
    active = "active"
    paused = "paused"
    ended = "ended"


class DiscountType(StrEnum):
    percentage = "percentage"
    fixed_amount = "fixed_amount"
```

### Matriz de transición de `CampaignStatus` (HARDCODEADA en el service, NO en BD)

```python
# services/campaign.py
CAMPAIGN_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.draft:  {CampaignStatus.active},
    CampaignStatus.active: {CampaignStatus.paused, CampaignStatus.ended},
    CampaignStatus.paused: {CampaignStatus.active, CampaignStatus.ended},
    CampaignStatus.ended:  set(),   # terminal
}
```

```
draft  → {active}
active → {paused, ended}
paused → {active, ended}
ended  → {}            # terminal
```

Transición no permitida → `BadRequestException(code="CAMPAIGN_TRANSITION_NOT_ALLOWED")` (400). La validación vive en `services/campaign.py:transition` (`to_status not in CAMPAIGN_TRANSITIONS[from_status]`). **No** hay side-effects ricos por estado destino (solo setea `status`), así que el endpoint genérico `POST /campaigns/{id}/transition` basta (no hay shortcuts tipo `/activate`, `/pause` — la UI manda el `to_status`).

## Models — SQLAlchemy 2.0

**Mixins** (de `app.shared.base_model`): `PrimaryKeyMixin` (`id` = `String(36)` PK uuid4), `ActiveMixin` (`active` = `Boolean NOT NULL default True`), `SoftDeleteMixin` (`deleted_at` = `DateTime(tz)` NULL), `TimestampMixin` (`created_on`/`updated_on` = `DateTime(tz) NOT NULL` + `created_by`/`updated_by` = `String(36) NOT NULL`, pasados EXPLÍCITO vía `actor_id`). MRO: `class X(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base)`, `Base` SIEMPRE último. `from __future__ import annotations` en todos los archivos.

> ⚠ **`PromotionUsage` NO lleva `SoftDeleteMixin`** — es un audit inmutable (append-only, igual que `appointment_status_history`/`lead_activity`). Las otras dos entidades (`Campaign`, `Promotion`) sí llevan los 4 mixins.

> ⚠ **Todas las FKs cross-módulo de `marketing` son REALES** (las tablas destino existen en prod: `vertical`, `product`, `person`, `appointment`) — a diferencia de `crm` que las dejó forward. Por eso `Campaign`/`Promotion`/`PromotionUsage` SÍ declaran `ForeignKey(...)` reales hacia ellas, pero **SIN `relationship` ORM cross-módulo** (se resuelven por id + batch maps + `vertical_repository.get_by_ids`/join propio a `Product`, igual que `scheduling` resuelve doctor/office sin relationship). El único `relationship` ORM es el M:N `Campaign.promotions ↔ Promotion.campaigns` (mismo módulo).

### `models/campaign.py` — tabla `campaign` — PK·A·SD·T

```python
"""
Campaign = una campaña de marketing (un esfuerzo comercial con vigencia y, vía el
M:N, un set de promociones). `code` es un slug estable en minúsculas (patrón
catalog.Vertical.code). `status` es CampaignStatus.value (varchar plano, NO catálogo);
las transiciones las valida el service contra la matriz hardcodeada. `target_vertical_id`
es FK REAL a catalog.vertical (NULL = campaña transversal a todas las verticales).
SIN relationship a Vertical (se resuelve target_vertical_name por vertical_repository.get_by_ids).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.marketing.enums import CampaignStatus
from app.modules.marketing.models.associations import campaign_promotion
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.marketing.models.promotion import Promotion


class Campaign(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "campaign"
    __table_args__ = (
        Index("ix_campaign_target_vertical", "target_vertical_id"),
        Index("ix_campaign_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # NULL = sin cierre conocido
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CampaignStatus.draft.value)
    # FK REAL a catalog.vertical (NULL = transversal). SIN relationship ORM.
    target_vertical_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vertical.id"), nullable=True
    )

    # ⚠ SUBSET F1: este relationship se DECLARA recién en F2 (Promotion aún no existe en F1).
    #    En F1 NO se declara (rompería el mapper). Ver §"Subset F1".
    promotions: Mapped[list[Promotion]] = relationship(
        secondary=campaign_promotion, back_populates="campaigns", lazy="raise"
    )
```

> El índice `uq_campaign_code` (UNIQUE no-parcial sobre `code`, igual que `catalog.vertical.code`) lo da `unique=True, index=True` en la columna. `get_by_code` filtra vivos. **NO** hay relationship a `Vertical`: `target_vertical_name`/`target_vertical` se resuelven con `vertical_repository.get_by_ids` batch + `VerticalOption.model_validate`.

### `models/promotion.py` — tabla `promotion` — PK·A·SD·T

```python
"""
Promotion = un descuento discriminado (percentage | fixed_amount). `discount_type`
es INMUTABLE post-create (no se cambia percentage↔fixed). `discount_value` es Decimal
Numeric(10,2): percentage 0<v≤100, fixed v>0 (validado en el SERVICE, no Pydantic, para
que update lo imponga uniforme). `currency` ISO 4217 (solo aplica si fixed_amount).
applies_to_all_products=true ignora el M:N promotion_product. SIN relationship a Product
(catalog, otro módulo) — el M:N promotion_product se resuelve por query propia.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.marketing.models.associations import campaign_promotion
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.marketing.models.campaign import Campaign


class Promotion(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "promotion"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)  # DiscountType.value — INMUTABLE
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PEN")  # ISO 4217 (solo fixed)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    max_uses_total: Mapped[int | None] = mapped_column(Integer, nullable=True)        # NULL = ilimitado
    max_uses_per_person: Mapped[int | None] = mapped_column(Integer, nullable=True)   # NULL = ilimitado
    applies_to_all_products: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    campaigns: Mapped[list[Campaign]] = relationship(
        secondary=campaign_promotion, back_populates="promotions", lazy="raise"
    )
```

> El índice `uq_promotion_code` lo da `unique=True, index=True`. **NO** hay relationship a `Product` (no tocar `catalog`): el M:N `promotion_product` se resuelve con un **join propio** en `PromotionProductRepository` (`WHERE promotion_id=X AND product.deleted_at IS NULL`).

### `models/promotion_usage.py` — tabla `promotion_usage` — PK·A·T (**SIN SoftDelete**, audit inmutable)

```python
"""
PromotionUsage = el registro INMUTABLE de una redención de promoción (audit append-only;
SIN SoftDeleteMixin). Snapshotea original/discount/final + currency al momento de aplicar
(no se recalcula nunca). created_on/created_by hacen de applied_at/applied_by (no hay columnas
separadas); aplicación automática (bot/scheduling) → created_by = SYSTEM_USER_ID.
NO stacking: UNIQUE PARCIAL sobre appointment_id WHERE appointment_id IS NOT NULL (una promo
por cita). Todas las FKs son REALES (las tablas existen) pero SIN relationship ORM.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class PromotionUsage(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "promotion_usage"
    __table_args__ = (
        Index("ix_promotion_usage_promotion", "promotion_id"),
        Index("ix_promotion_usage_person", "person_id"),
        Index("ix_promotion_usage_product", "product_id"),
        Index("ix_promotion_usage_appointment", "appointment_id"),
        Index("ix_promotion_usage_campaign", "campaign_id"),
        Index("ix_promotion_usage_created_on", "created_on"),
        # NO stacking: una promo por cita. UNIQUE PARCIAL dialect-agnóstico (lección crm F1):
        # postgresql_where para prod, sqlite_where para el smoke. SIN cláusula deleted_at
        # (no hay SoftDelete en esta tabla).
        Index(
            "uq_promotion_usage_appointment",
            "appointment_id",
            unique=True,
            postgresql_where=text("appointment_id IS NOT NULL"),
            sqlite_where=text("appointment_id IS NOT NULL"),
        ),
    )

    promotion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("promotion.id"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product.id"), nullable=False
    )
    # NULL = redención sin cita. FK REAL a scheduling.appointment.
    appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointment.id"), nullable=True
    )
    # NULL = sin campaña asociada. FK REAL a campaign.
    campaign_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("campaign.id"), nullable=True
    )
    original_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # snapshot base_price
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # monto descontado
    final_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)     # original - discount
    currency: Mapped[str] = mapped_column(String(3), nullable=False)                  # snapshot product.currency
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

> `from sqlalchemy import text` para los `*_where`. El `Index(..., unique=True, postgresql_where=..., sqlite_where=...)` se traduce en la migración a `CREATE UNIQUE INDEX uq_promotion_usage_appointment ON promotion_usage (appointment_id) WHERE appointment_id IS NOT NULL`. **NO** lleva `deleted_at IS NULL` (no hay SoftDelete). El service hace un chequeo proactivo `PROMOTION_ALREADY_APPLIED` (409) y la BD lo respalda con el índice (backstop de carrera).

### `models/associations.py` — M:N

```python
"""
M:N de marketing. PK compuesta + FK CASCADE (borrar la promo/campaña/producto limpia
sus vínculos). campaign_promotion vincula campañas con promociones (relationship ORM en
ambos lados). promotion_product vincula promociones con productos de catalog (SIN
relationship en Product — se resuelve por join propio en el repo).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

campaign_promotion = Table(
    "campaign_promotion",
    Base.metadata,
    Column("campaign_id", String(36), ForeignKey("campaign.id", ondelete="CASCADE"), primary_key=True),
    Column("promotion_id", String(36), ForeignKey("promotion.id", ondelete="CASCADE"), primary_key=True),
)

promotion_product = Table(
    "promotion_product",
    Base.metadata,
    Column("promotion_id", String(36), ForeignKey("promotion.id", ondelete="CASCADE"), primary_key=True),
    Column("product_id", String(36), ForeignKey("product.id", ondelete="CASCADE"), primary_key=True),
)
```

### `models/__init__.py`

```python
"""
Importar los modelos acá los registra en Base.metadata antes de que Alembic lea el
esquema y antes de resolver los relationship() por string. Orden: associations +
campaign + promotion antes que promotion_usage.

⚠ SUBSET F1: en F1, este __init__ importa SOLO campaign (y associations.campaign_promotion
queda referenciada pero su tabla la crea F2). promotion/promotion_usage se agregan en F2/F3.
El relationship Campaign.promotions se declara recién en F2 (cuando Promotion existe).
"""

from app.modules.marketing.models.associations import (  # noqa: F401
    campaign_promotion,
    promotion_product,
)
from app.modules.marketing.models.campaign import Campaign
from app.modules.marketing.models.promotion import Promotion
from app.modules.marketing.models.promotion_usage import PromotionUsage

__all__ = ["Campaign", "Promotion", "PromotionUsage", "campaign_promotion", "promotion_product"]
```

**Lazy strategy**: como en `crm`/`scheduling`, el único relationship ORM (`Campaign.promotions ↔ Promotion.campaigns`) es `lazy="raise"` — se carga con `selectinload(...)` explícito en el repo cuando se necesita el detalle, nunca implícitamente. Las FKs cross-módulo (`target_vertical_id`, `product_id`, `person_id`, `appointment_id`, `campaign_id`) NO tienen relationship: se resuelven por id + batch maps.

---

## ⚠ SUBSET F1 — Campaign sin `promotions` hasta F2

`Campaign` y `Promotion` se conocen vía el M:N `campaign_promotion`. **En F1, `Promotion` aún no existe** → declarar el `relationship` (o importar `Promotion`) rompería el mapper al boot. Por eso (igual que `crm` difirió FKs forward):

- **F1**: `models/campaign.py` **NO** declara `promotions: Mapped[list[Promotion]]` ni importa `Promotion`. `models/__init__.py` importa SOLO `Campaign` (no `Promotion`/`PromotionUsage`). La migración `0022` crea `campaign` (NO `campaign_promotion` todavía).
- **F1 schemas**: `CampaignDetail.promotions` se DECLARA (campo `list[PromotionOption]`) pero el service devuelve `[]`. `promotions_count` = `0` en F1. El endpoint `GET /campaigns/{id}/promotions` y `PUT /campaigns/{id}/promotions` (set) llegan en F2.
- **F2**: se agrega `promotions` relationship en `Campaign` (ya existe `Promotion`), `models/__init__.py` importa `Promotion`, la migración `0023` crea `promotion` + `campaign_promotion` + `promotion_product`. Se activan `promotions_count` (Campaign), `products_count`/`campaigns_count` (Promotion), el M:N y `set_promotions`/`set_products`.

---

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (idénticas a [`../crm/backend.md`](../crm/backend.md#schemas-pydantic-v2--completos)):
>
> 1. **No usar Ellipsis (`...`)** en `Field(...)`. Campo sin `default=` ya es obligatorio.
> 2. **`Annotated`** solo para parámetros HTTP (`Query`, `Path`) en routers.
> 3. **Validators**: `@field_validator` single-field, `@model_validator(mode="after")` cross-field. **El rango `discount_type↔discount_value` NO se valida en Pydantic** (vive en el SERVICE, para que `update` sin `discount_type` lo imponga uniforme).
> 4. **Mensajes de validator en inglés** (van al detalle 422). El texto user-facing en español vive en el Zod del frontend.
> 5. **Decimal → string en el wire**: `discount_value`/`*_amount` son `Decimal` en Pydantic; Pydantic v2 los serializa como string en el JSON. TS los tipa `string`.

### `schemas/campaign.py`

```python
from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption  # FK cross-módulo (read)
from app.modules.marketing.enums import CampaignStatus

# Slug en minúsculas/dígitos/_/- (patrón catalog.Vertical.code). Inmutable post-create.
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")


class CampaignOption(BaseModel):
    """Dropdown / M:N / atribución — id/code/name/status."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    status: CampaignStatus


class CampaignCreate(BaseModel):
    """status NO va (nace draft). target_vertical_id opcional (NULL = transversal)."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    start_date: date_type
    end_date: date_type | None = None
    target_vertical_id: str | None = None

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError("code must be a lowercase slug: letras minúsculas, números y guion bajo (sin guiones)")
        return v


class CampaignUpdate(BaseModel):
    """`code` y `status` inmutables vía update (status se cambia por /transition)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    start_date: date_type | None = None
    end_date: date_type | None = None
    target_vertical_id: str | None = None
    active: bool | None = None


class CampaignTransitionRequest(BaseModel):
    """Body de POST /campaigns/{id}/transition (valida la matriz hardcodeada)."""

    to_status: CampaignStatus


class CampaignPromotionsReplace(BaseModel):
    """Body de PUT /campaigns/{id}/promotions — bulk-replace de las promos del M:N."""

    promotion_ids: list[str] = Field(default_factory=list)

    @field_validator("promotion_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("promotion_ids must not contain duplicates")
        return v


class CampaignItem(BaseModel):
    """Fila de la tabla de campañas. Denormaliza target_vertical_name + promotions_count
    para que la lista no joinee (NINGUNO va en ALLOWED_FIELDS — lección cd10c78)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    start_date: date_type
    end_date: date_type | None
    status: CampaignStatus
    target_vertical_id: str | None
    target_vertical_name: str | None = None  # denorm de catalog.Vertical.name
    promotions_count: int  # 0 en F1 (sin M:N todavía)
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class CampaignDetail(CampaignItem):
    """Detalle: agrega la vertical resuelta + las promos del M:N (read-only en el detalle;
    se editan por PUT /campaigns/{id}/promotions). En F1 promotions = []."""

    target_vertical: VerticalOption | None = None
    promotions: list[PromotionOption]  # de schemas/promotion.py (forward-ref en F1)
```

> `CampaignDetail.promotions` referencia `PromotionOption` (de `schemas/promotion.py`); en F1 se declara como forward-ref string y el service devuelve `[]` (no hay M:N). En F2 se importa `PromotionOption` y al pie del módulo se hace `CampaignDetail.model_rebuild()` si el import cruzado molesta. `target_vertical`/`target_vertical_name` los arma el service (no salen de un attribute del modelo: `Campaign` no tiene relationship a `Vertical`).

### `schemas/promotion.py`

```python
from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.product import ProductOption  # FK cross-módulo (read)
from app.modules.marketing.enums import DiscountType
from app.modules.marketing.schemas.campaign import CampaignOption

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")  # ISO 4217


class PromotionOption(BaseModel):
    """Molde de ProductOption — trae el descuento listo para mostrar (selects, M:N de campaña)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    discount_type: DiscountType
    discount_value: Decimal
    currency: str


class PromotionCreate(BaseModel):
    """El rango discount_type↔discount_value se valida en el SERVICE (no acá), para que
    update (sin discount_type) lo imponga uniforme."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    discount_type: DiscountType
    discount_value: Decimal = Field(max_digits=10, decimal_places=2)
    currency: str = "PEN"
    start_date: date_type
    end_date: date_type | None = None
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_person: int | None = Field(default=None, ge=1)
    applies_to_all_products: bool = False

    @field_validator("code")
    @classmethod
    def _code_slug(cls, v: str) -> str:
        if not CODE_PATTERN.fullmatch(v):
            raise ValueError("code must be a lowercase slug: letras minúsculas, números y guion bajo (sin guiones)")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_iso(cls, v: str) -> str:
        if not CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be an ISO 4217 code (3 uppercase letters)")
        return v


class PromotionUpdate(BaseModel):
    """`code` y `discount_type` inmutables vía update (no se declaran)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    discount_value: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    currency: str | None = None
    start_date: date_type | None = None
    end_date: date_type | None = None
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_person: int | None = Field(default=None, ge=1)
    applies_to_all_products: bool | None = None
    active: bool | None = None

    @field_validator("currency")
    @classmethod
    def _currency_iso(cls, v: str | None) -> str | None:
        if v is not None and not CURRENCY_PATTERN.fullmatch(v):
            raise ValueError("currency must be an ISO 4217 code (3 uppercase letters)")
        return v


class PromotionProductsReplace(BaseModel):
    """Body de PUT /promotions/{id}/products — bulk-replace del M:N de productos."""

    product_ids: list[str] = Field(default_factory=list)

    @field_validator("product_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("product_ids must not contain duplicates")
        return v


class PromotionItem(BaseModel):
    """Fila de la tabla. Denormaliza products_count/campaigns_count (NO en ALLOWED_FIELDS)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    discount_type: DiscountType
    discount_value: Decimal
    currency: str
    start_date: date_type
    end_date: date_type | None
    max_uses_total: int | None
    max_uses_per_person: int | None
    applies_to_all_products: bool
    products_count: int     # 0 si applies_to_all_products=true
    campaigns_count: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class PromotionDetail(PromotionItem):
    """Detalle: productos (vacío si applies_to_all_products), campañas (read-only), total_uses."""

    products: list[ProductOption]      # vacío si applies_to_all_products=true
    campaigns: list[CampaignOption]    # read-only (se editan desde la campaña)
    total_uses: int
```

### `schemas/promotion_usage.py` (PromotionUsage + validación / precio)

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.marketing.schemas.promotion import PromotionOption


class PromotionUsageItem(BaseModel):
    """Fila de la tabla de usos (read-only). Denormaliza promotion/person/product/campaign
    names + los montos snapshot. SIN updated_on (audit inmutable). SIN updated_by_user."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    promotion_id: str
    promotion_name: str   # denorm
    person_id: str
    person_name: str      # denorm (crm.Person full_name vía person_option_map)
    product_id: str
    product_name: str     # denorm (catalog.Product.name)
    appointment_id: str | None
    campaign_id: str | None
    campaign_name: str | None  # denorm (NULL si campaign_id NULL)
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    currency: str
    notes: str | None
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None


class PromotionUsageDetail(PromotionUsageItem):
    """= Item; sin extras hoy."""


class ApplyPromotionRequest(BaseModel):
    """Body de POST /promotion-usages — crea un PromotionUsage (redención)."""

    promotion_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    appointment_id: str | None = None
    campaign_id: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class PromotionEligibilityRequest(BaseModel):
    """Body de POST /promotions/eligible-for — qué promos aplican a (product, person)."""

    product_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)


class PromotionEligibility(BaseModel):
    """Una promo evaluada para (product, person) — sin insertar nada."""

    promotion_id: str
    code: str
    name: str
    is_eligible: bool
    reason: str | None = None  # code del primer motivo de inelegibilidad (None si elegible)
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    currency: str


class ComputePriceRequest(BaseModel):
    """Body de POST /compute-price — precio final con/sin una promo puntual."""

    product_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    promotion_id: str | None = None


class ComputePriceResponse(BaseModel):
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    currency: str
    promotion: PromotionOption | None = None  # None si no se pidió promo


class PromotionUsageSummary(BaseModel):
    """Resumen de uso de una promo — GET /promotions/{id}/usage-summary."""

    promotion_id: str
    total_uses: int
    total_original_amount: Decimal
    total_discount_amount: Decimal
    total_final_amount: Decimal
```

## Repositories

`ALLOWED_FIELDS` es el whitelist de columnas filtrable/ordenable desde el frontend (ver [`backend/CLAUDE.md`](../../../backend/CLAUDE.md)). **Lección hotfix `cd10c78` de `staff`**: solo columnas **reales** de la tabla — nunca campos denormalizados (`target_vertical_name`, `promotions_count`, `promotion_name`, …). Cada repo expone un singleton al pie (`campaign_repository = CampaignRepository()`, etc.).

### `repositories/campaign.py`

```python
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.marketing.models.campaign import Campaign
from app.shared.base_repository import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    # SOLO columnas reales de `campaign`. target_vertical_name/promotions_count DENORM → NO.
    # Default sort = created_on desc.
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "status", "start_date", "end_date",
        "target_vertical_id", "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Campaign)

    async def get_by_code(self, db: AsyncSession, code: str) -> Campaign | None:
        result = await db.execute(
            select(Campaign).where(Campaign.code == code, Campaign.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Campaign]:
        """status='active' + vivos, order name. GET /campaigns/active (lista cruda)."""
        result = await db.execute(
            select(Campaign)
            .where(
                Campaign.status == "active",
                Campaign.active.is_(True),
                Campaign.deleted_at.is_(None),
            )
            .order_by(Campaign.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Campaign]:
        """Batch (patrón vertical_repository.get_by_ids)."""
        if not ids:
            return []
        result = await db.execute(
            select(Campaign).where(Campaign.id.in_(ids), Campaign.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def campaign_name_map(self, db: AsyncSession, ids: list[str]) -> dict[str, str]:
        """Batch id→name para denormalizar campaign_name en PromotionUsageItem."""
        if not ids:
            return {}
        result = await db.execute(
            select(Campaign.id, Campaign.name).where(
                Campaign.id.in_(ids), Campaign.deleted_at.is_(None)
            )
        )
        return {row[0]: row[1] for row in result.all()}


campaign_repository = CampaignRepository()
```

### `repositories/promotion.py`

```python
class PromotionRepository(BaseRepository[Promotion]):
    ALLOWED_FIELDS: set[str] = {
        "code", "name", "discount_type", "currency", "start_date", "end_date",
        "applies_to_all_products", "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Promotion)

    async def get_by_code(self, db: AsyncSession, code: str) -> Promotion | None:
        result = await db.execute(
            select(Promotion).where(Promotion.code == code, Promotion.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Promotion]:
        result = await db.execute(
            select(Promotion)
            .where(Promotion.active.is_(True), Promotion.deleted_at.is_(None))
            .order_by(Promotion.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Promotion]:
        if not ids:
            return []
        result = await db.execute(
            select(Promotion).where(Promotion.id.in_(ids), Promotion.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def get_for_update(self, db: AsyncSession, promotion_id: str) -> Promotion | None:
        """SELECT ... FOR UPDATE para serializar el chequeo de max_uses en apply
        (Postgres-only; no-op en sqlite/smoke). Usar SIEMPRE en apply por simplicidad."""
        result = await db.execute(
            select(Promotion)
            .where(Promotion.id == promotion_id, Promotion.deleted_at.is_(None))
            .with_for_update()
        )
        return result.scalars().first()

    async def promotion_name_map(self, db: AsyncSession, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        result = await db.execute(
            select(Promotion.id, Promotion.name).where(
                Promotion.id.in_(ids), Promotion.deleted_at.is_(None)
            )
        )
        return {row[0]: row[1] for row in result.all()}


promotion_repository = PromotionRepository()
```

### `repositories/campaign_promotion.py` (M:N `campaign_promotion`)

```python
from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.marketing.models.associations import campaign_promotion


class CampaignPromotionRepository:
    async def promotion_ids_for_campaign(self, db: AsyncSession, campaign_id: str) -> list[str]:
        result = await db.execute(
            select(campaign_promotion.c.promotion_id).where(
                campaign_promotion.c.campaign_id == campaign_id
            )
        )
        return [row[0] for row in result.all()]

    async def campaign_ids_for_promotion(self, db: AsyncSession, promotion_id: str) -> list[str]:
        result = await db.execute(
            select(campaign_promotion.c.campaign_id).where(
                campaign_promotion.c.promotion_id == promotion_id
            )
        )
        return [row[0] for row in result.all()]

    async def set_promotions(
        self, db: AsyncSession, campaign_id: str, promotion_ids: list[str]
    ) -> None:
        """Bulk-replace: delete todas las del campaign + insert el nuevo set. Una tx
        (molde bots.bot_tool / staff M:N). El caller valida que cada promo exista viva."""
        await db.execute(
            delete(campaign_promotion).where(campaign_promotion.c.campaign_id == campaign_id)
        )
        if promotion_ids:
            await db.execute(
                insert(campaign_promotion),
                [{"campaign_id": campaign_id, "promotion_id": pid} for pid in promotion_ids],
            )

    async def count_promotions_map(
        self, db: AsyncSession, campaign_ids: list[str]
    ) -> dict[str, int]:
        """Batch campaign_id→#promos para CampaignItem.promotions_count."""
        if not campaign_ids:
            return {}
        result = await db.execute(
            select(campaign_promotion.c.campaign_id, func.count())
            .where(campaign_promotion.c.campaign_id.in_(campaign_ids))
            .group_by(campaign_promotion.c.campaign_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_campaigns_map(
        self, db: AsyncSession, promotion_ids: list[str]
    ) -> dict[str, int]:
        """Batch promotion_id→#campañas para PromotionItem.campaigns_count."""
        if not promotion_ids:
            return {}
        result = await db.execute(
            select(campaign_promotion.c.promotion_id, func.count())
            .where(campaign_promotion.c.promotion_id.in_(promotion_ids))
            .group_by(campaign_promotion.c.promotion_id)
        )
        return {row[0]: row[1] for row in result.all()}


campaign_promotion_repository = CampaignPromotionRepository()
```

### `repositories/promotion_product.py` (M:N `promotion_product` + **join propio a `catalog.Product`**)

```python
from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models.product import Product  # solo para el join de lectura
from app.modules.marketing.models.associations import promotion_product


class PromotionProductRepository:
    async def product_ids_for_promotion(self, db: AsyncSession, promotion_id: str) -> list[str]:
        result = await db.execute(
            select(promotion_product.c.product_id).where(
                promotion_product.c.promotion_id == promotion_id
            )
        )
        return [row[0] for row in result.all()]

    async def set_products(
        self, db: AsyncSession, promotion_id: str, product_ids: list[str]
    ) -> None:
        """Bulk-replace. El caller valida que cada product exista vivo en catalog."""
        await db.execute(
            delete(promotion_product).where(promotion_product.c.promotion_id == promotion_id)
        )
        if product_ids:
            await db.execute(
                insert(promotion_product),
                [{"promotion_id": promotion_id, "product_id": pid} for pid in product_ids],
            )

    async def count_products_map(
        self, db: AsyncSession, promotion_ids: list[str]
    ) -> dict[str, int]:
        if not promotion_ids:
            return {}
        result = await db.execute(
            select(promotion_product.c.promotion_id, func.count())
            .where(promotion_product.c.promotion_id.in_(promotion_ids))
            .group_by(promotion_product.c.promotion_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def list_products_for_promotion(
        self, db: AsyncSession, promotion_id: str
    ) -> list[Product]:
        """JOIN PROPIO a catalog.Product (NO relationship en Product — no tocar catalog).
        Solo productos vivos. Powers PromotionDetail.products."""
        result = await db.execute(
            select(Product)
            .join(promotion_product, promotion_product.c.product_id == Product.id)
            .where(
                promotion_product.c.promotion_id == promotion_id,
                Product.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def covers_product(
        self, db: AsyncSession, promotion_id: str, product_id: str
    ) -> bool:
        """¿El producto está en el M:N de la promo? (apply paso 5, cuando NOT applies_to_all)."""
        result = await db.execute(
            select(promotion_product.c.product_id).where(
                promotion_product.c.promotion_id == promotion_id,
                promotion_product.c.product_id == product_id,
            )
        )
        return result.scalars().first() is not None


promotion_product_repository = PromotionProductRepository()
```

### `repositories/promotion_usage.py`

```python
class PromotionUsageRepository(BaseRepository[PromotionUsage]):
    # SIN updated_on (audit inmutable). Default sort = created_on desc.
    ALLOWED_FIELDS: set[str] = {
        "promotion_id", "person_id", "product_id", "appointment_id",
        "campaign_id", "currency", "created_on",
    }

    def __init__(self) -> None:
        super().__init__(PromotionUsage)

    async def get_by_appointment(
        self, db: AsyncSession, appointment_id: str
    ) -> PromotionUsage | None:
        """Pre-check no-stacking (apply paso 6). El UNIQUE parcial es el backstop."""
        result = await db.execute(
            select(PromotionUsage).where(PromotionUsage.appointment_id == appointment_id)
        )
        return result.scalars().first()

    async def count_for_promotion(self, db: AsyncSession, promotion_id: str) -> int:
        """max_uses_total (apply paso 7)."""
        result = await db.execute(
            select(func.count())
            .select_from(PromotionUsage)
            .where(PromotionUsage.promotion_id == promotion_id)
        )
        return result.scalar_one()

    async def count_for_promotion_person(
        self, db: AsyncSession, promotion_id: str, person_id: str
    ) -> int:
        """max_uses_per_person (apply paso 8)."""
        result = await db.execute(
            select(func.count())
            .select_from(PromotionUsage)
            .where(
                PromotionUsage.promotion_id == promotion_id,
                PromotionUsage.person_id == person_id,
            )
        )
        return result.scalar_one()

    async def usage_summary(self, db: AsyncSession, promotion_id: str):
        """Row(count, sum_original, sum_discount, sum_final) — GET /usage-summary."""
        result = await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(PromotionUsage.original_amount), 0),
                func.coalesce(func.sum(PromotionUsage.discount_amount), 0),
                func.coalesce(func.sum(PromotionUsage.final_amount), 0),
            ).where(PromotionUsage.promotion_id == promotion_id)
        )
        return result.one()


promotion_usage_repository = PromotionUsageRepository()
```

### Lecturas cross-módulo (sin tocar otros módulos)

`marketing` LEE (nunca escribe) de otros módulos:
- `catalog.product_repository.get_by_id(db, product_id)` → 1 producto (`base_price` + `currency` para el cálculo).
- `catalog.vertical_repository.get_by_ids(db, ids)` + `VerticalOption.model_validate(...)` → `target_vertical_name`/`target_vertical`.
- `crm.person_repository.get_by_id(db, person_id)` → existencia (apply paso 4) + `crm.services.person.person_option_map(db, ids)` → `person_name` en los reportes de uso.
- `admin.user_repository.get_audit_info_map(db, ids)` → audit (`created_by_user`/`updated_by_user`).

Ninguna de estas lecturas modifica los otros módulos. (Solo F4 toca `scheduling`/`bots` en código — ver §F4.)

## Services — `services/*.py` (módulos de funciones)

> Patrón shipped: cada función recibe `AsyncSession` + `actor_id` explícito, devuelve un response schema, lanza excepciones de dominio (nunca `HTTPException`), reload-via-get tras create/update, NO commitea (`get_db` commitea al final del request). Denormalización por batch maps (cero N+1). Audit users vía `get_audit_info_map`.

### `services/campaign.py`

```python
CAMPAIGN_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.draft:  {CampaignStatus.active},
    CampaignStatus.active: {CampaignStatus.paused, CampaignStatus.ended},
    CampaignStatus.paused: {CampaignStatus.active, CampaignStatus.ended},
    CampaignStatus.ended:  set(),
}
```

| Función | Firma | Invariantes / error codes |
|---|---|---|
| `list_paginated` | `(db, query) -> PaginatedResponse[CampaignItem]` | `get_paginated` + batch (`target_vertical_name` vía `vertical_repository.get_by_ids`, `promotions_count` vía `count_promotions_map` [0 en F1], audit). |
| `get_by_id` | `(db, id) -> SingleResponse[CampaignDetail]` | NotFound `CAMPAIGN_NOT_FOUND` (404). |
| `create` | `(db, payload, *, actor_id) -> SingleResponse[CampaignDetail]` | `code` único → `AlreadyExists CAMPAIGN_CODE_TAKEN` (409); `end_date >= start_date` (si end) → else `BadRequest CAMPAIGN_INVALID_DATES` (400); `target_vertical_id` (si provisto) existe vivo → else `BadRequest TARGET_VERTICAL_NOT_FOUND` (400). `status='draft'`. |
| `update` | `(db, id, payload, *, actor_id) -> SingleResponse[CampaignDetail]` | Mismas validaciones de fecha/vertical sobre el merge. NO cambia `code`/`status`. |
| `transition` | `(db, id, to_status, *, actor_id) -> SingleResponse[CampaignDetail]` | `to_status not in CAMPAIGN_TRANSITIONS[campaign.status]` → `BadRequest CAMPAIGN_TRANSITION_NOT_ALLOWED` (400). Setea `status`. |
| `remove` | `(db, id, *, actor_id) -> None` | `soft_delete`. **Sin guard de hijos** (ver nota). |
| `list_active` | `(db) -> list[CampaignOption]` | raw, sin envelope. |
| `get_promotions` | `(db, id) -> SingleResponse[list[PromotionOption]]` | las promos del M:N (F2). |
| `set_promotions` | `(db, id, promotion_ids, *, actor_id) -> SingleResponse[CampaignDetail]` | cada `promotion_id` existe vivo → else `BadRequest PROMOTION_NOT_FOUND` (404); bulk-replace (F2). |

> **`remove` sin guard de hijos** (decisión documentada): el soft-delete de una campaña es libre. Los `PromotionUsage` que la referencian son audit histórico y conservan su `campaign_id` — la FK no se rompe porque la fila `campaign` queda VIVA (solo `deleted_at` no nulo). El M:N `campaign_promotion` persiste (no se desvinculan las promos; soft-delete no dispara el `CASCADE`, que es solo de hard-delete). Esto se documenta para que el reviewer no lo marque como bug.

```python
async def transition(db, campaign_id, to_status: CampaignStatus, *, actor_id):
    campaign = await campaign_repository.get_by_id(db, campaign_id)
    if campaign is None:
        raise NotFoundException("Campaña no encontrada", code="CAMPAIGN_NOT_FOUND")
    current = CampaignStatus(campaign.status)
    if to_status not in CAMPAIGN_TRANSITIONS[current]:
        raise BadRequestException(
            f"Transición de campaña no permitida: de '{current.value}' a '{to_status.value}'",
            code="CAMPAIGN_TRANSITION_NOT_ALLOWED")
    campaign.status = to_status.value
    campaign.updated_by = actor_id
    campaign.updated_on = utc_now()
    await db.flush()
    return SingleResponse(data=await _to_detail(db, campaign))
```

### `services/promotion.py`

```python
def _validate_discount(discount_type: DiscountType, discount_value: Decimal) -> None:
    """Validación del rango en el SERVICE (create Y update). En update, discount_type =
    el de la fila existente (inmutable), discount_value = payload o existente."""
    if discount_type == DiscountType.percentage:
        if not (Decimal("0") < discount_value <= Decimal("100")):
            raise BadRequestException(
                "El porcentaje debe estar entre 0 y 100", code="PROMOTION_INVALID_DISCOUNT")
    else:  # fixed_amount
        if discount_value <= Decimal("0"):
            raise BadRequestException(
                "El monto fijo debe ser mayor que 0", code="PROMOTION_INVALID_DISCOUNT")
```

| Función | Firma | Invariantes / error codes |
|---|---|---|
| `list_paginated` | `(db, query) -> PaginatedResponse[PromotionItem]` | batch `products_count`/`campaigns_count` + audit. |
| `get_by_id` | `(db, id) -> SingleResponse[PromotionDetail]` | NotFound `PROMOTION_NOT_FOUND` (404). |
| `create` | `(db, payload, *, actor_id) -> SingleResponse[PromotionDetail]` | `_validate_discount(payload.discount_type, payload.discount_value)` → `PROMOTION_INVALID_DISCOUNT` (400); `code` único → `PROMOTION_CODE_TAKEN` (409); fechas → `PROMOTION_INVALID_DATES` (400). |
| `update` | `(db, id, payload, *, actor_id) -> SingleResponse[PromotionDetail]` | `_validate_discount(existing.discount_type, payload.discount_value or existing.discount_value)`; fechas sobre el merge. NO cambia `code`/`discount_type`. |
| `remove` | `(db, id, *, actor_id) -> None` | `soft_delete`. |
| `list_active` | `(db) -> list[PromotionOption]` | raw. |
| `get_products` | `(db, id) -> SingleResponse[list[ProductOption]]` | `list_products_for_promotion` (join propio). |
| `set_products` | `(db, id, product_ids, *, actor_id) -> SingleResponse[PromotionDetail]` | cada `product_id` vivo en catalog → else `BadRequest PRODUCT_NOT_FOUND` (404); bulk-replace. |
| `usage_summary` | `(db, id) -> SingleResponse[PromotionUsageSummary]` | `usage_summary` repo (count + sums). |

### `services/promotion_usage.py` (el corazón de F3)

#### `apply` — los 10 pasos (en SERVICE, con code)

```python
async def apply(db, *, promotion_id, person_id, product_id, appointment_id=None,
                campaign_id=None, actor_id, notes=None) -> SingleResponse[PromotionUsageDetail]:
    # 1) Lock de la promo (max_uses). get_for_update SIEMPRE (no-op en sqlite).
    promo = await promotion_repository.get_for_update(db, promotion_id)
    if promo is None:
        raise NotFoundException("Promoción no encontrada", code="PROMOTION_NOT_FOUND")
    # 2) activa + vigente.
    today = date.today()
    if not promo.active:
        raise BadRequestException("La promoción no está activa", code="PROMOTION_NOT_ACTIVE")
    if promo.start_date > today or (promo.end_date is not None and promo.end_date < today):
        raise BadRequestException("La promoción está fuera de vigencia", code="PROMOTION_EXPIRED")
    # 3) producto (base_price + currency).
    product = await catalog_product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    base_price = product.base_price
    currency = product.currency
    # 4) persona existe.
    person = await crm_person_repository.get_by_id(db, person_id)
    if person is None:
        raise NotFoundException("Persona no encontrada", code="PERSON_NOT_FOUND")
    # 5) cobertura (si NO aplica a todos los productos).
    if not promo.applies_to_all_products:
        if not await promotion_product_repository.covers_product(db, promotion_id, product_id):
            raise BadRequestException(
                "La promoción no cubre este producto", code="PROMOTION_PRODUCT_NOT_COVERED")
    # 6) no-stacking (si hay cita).
    if appointment_id is not None:
        existing = await promotion_usage_repository.get_by_appointment(db, appointment_id)
        if existing is not None:
            raise ConflictException(
                "Ya se aplicó una promoción a esta cita", code="PROMOTION_ALREADY_APPLIED")
    # 7) max_uses_total.
    if promo.max_uses_total is not None:
        if await promotion_usage_repository.count_for_promotion(db, promotion_id) >= promo.max_uses_total:
            raise BadRequestException(
                "La promoción alcanzó su límite de usos", code="PROMOTION_LIMIT_REACHED")
    # 8) max_uses_per_person.
    if promo.max_uses_per_person is not None:
        used = await promotion_usage_repository.count_for_promotion_person(db, promotion_id, person_id)
        if used >= promo.max_uses_per_person:
            raise BadRequestException(
                "La persona alcanzó su límite de usos de la promoción",
                code="PROMOTION_PERSON_LIMIT_REACHED")
    # 9) cálculo (Decimal, ROUND_HALF_UP, cap a base_price).
    discount = _compute_discount(promo, base_price)
    final = base_price - discount
    # 10) insertar el PromotionUsage (snapshot). created_by/updated_by = actor_id.
    now = utc_now()
    usage = PromotionUsage(
        id=generate_uuid(), promotion_id=promotion_id, person_id=person_id,
        product_id=product_id, appointment_id=appointment_id, campaign_id=campaign_id,
        original_amount=base_price, discount_amount=discount, final_amount=final,
        currency=currency, notes=notes, active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now)
    db.add(usage); await db.flush()
    return SingleResponse(data=await _to_detail(db, usage))
```

#### `_compute_discount` — helper puro (Decimal, ROUND_HALF_UP, cap)

```python
def _compute_discount(promo: Promotion, base_price: Decimal) -> Decimal:
    """Puro, testeable. percentage: base_price * value/100 (ROUND_HALF_UP 2dp), cap a base_price.
    fixed: min(value, base_price). Un descuento NUNCA supera el precio."""
    if promo.discount_type == DiscountType.percentage.value:
        raw = (base_price * promo.discount_value / Decimal("100"))
        discount = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:  # fixed_amount
        discount = promo.discount_value
    return min(discount, base_price)
```

#### `eligible_for` / `validate` / `compute_price` (read-only, NO insertan)

| Función | Firma | Notas |
|---|---|---|
| `eligible_for` | `(db, *, product_id, person_id) -> SingleResponse[list[PromotionEligibility]]` | Lista promos activas+vigentes que cubren el producto (`applies_to_all_products` OR en `promotion_product`); para cada una corre la lógica de elegibilidad SIN insertar: `is_eligible` + `reason` (code de `PROMOTION_EXPIRED`/`PROMOTION_LIMIT_REACHED`/`PROMOTION_PERSON_LIMIT_REACHED`/`PROMOTION_NOT_ACTIVE`) + amounts. Gated `PROMOTION_VALIDATE`. |
| `validate` | `(db, *, promotion_id, product_id, person_id) -> SingleResponse[PromotionEligibility]` | Una promo puntual (mismo cálculo, sin insertar). |
| `compute_price` | `(db, *, product_id, person_id, promotion_id=None) -> SingleResponse[ComputePriceResponse]` | Si `promotion_id` → valida + aplica el cálculo (sin insertar; promotion = `PromotionOption`); si None → `original=final`, `discount=0`, `promotion=None`. |
| `list_paginated` | `(db, query) -> PaginatedResponse[PromotionUsageItem]` | batch `promotion_name`, `person_name` (vía `person_option_map`), `product_name`, `campaign_name`, audit. |

> `eligible_for`/`validate`/`compute_price` comparten un helper interno de evaluación con `apply` (la lógica de pasos 2/5/7/8 + `_compute_discount`), pero en modo "dry-run": en vez de lanzar, capturan el primer code y lo devuelven como `reason` (`is_eligible=false`). El producto/persona inexistentes SÍ lanzan `PRODUCT_NOT_FOUND`/`PERSON_NOT_FOUND` (no son "inelegibilidad", son input inválido). Mismo patrón que `scheduling.check_slot` vs `create_appointment`.

## API contracts

Envelopes del template (idénticos a [`../crm/backend.md`](../crm/backend.md#api-contracts)):
- **Single**: `{ "success": true, "data": <T> }`
- **Paginated**: `{ "success": true, "data": { "items": [...], "total": N, "skip": 0, "limit": 10 } }`
- **Lista cruda** (`/active`): el body es directamente `[...]`.
- **Error**: `{ "success": false, "detail": "...", "code"?: "...", "errors"?: [...] }`

Prefijo común: `/api/v1/marketing/`. Listados paginados con `POST /<recurso>/list` + `QueryRequest`. `PUT` (no `PATCH`); `/active` y los literales (`eligible-for`) antes de `/{id}` en el router. **Decimales serializan como STRING** en todos los JSON de abajo.

### Campaign (`routers/campaign.py`, prefix `/campaigns`)

| Método | Ruta | Permiso | Response |
|---|---|---|---|
| POST | `/campaigns/list` | `CAMPAIGNS_READ` | `PaginatedResponse[CampaignItem]` |
| POST | `/campaigns` (201) | `CAMPAIGNS_CREATE` | `SingleResponse[CampaignDetail]` |
| GET | `/campaigns/active` | `CAMPAIGNS_READ` | lista cruda `list[CampaignOption]` |
| GET | `/campaigns/{id}` | `CAMPAIGNS_READ` | `SingleResponse[CampaignDetail]` |
| PUT | `/campaigns/{id}` | `CAMPAIGNS_UPDATE` | `SingleResponse[CampaignDetail]` |
| DELETE | `/campaigns/{id}` (204) | `CAMPAIGNS_DELETE` | — |
| POST | `/campaigns/{id}/transition` | `CAMPAIGNS_UPDATE` | `SingleResponse[CampaignDetail]` |
| GET | `/campaigns/{id}/promotions` | `CAMPAIGNS_READ` | `SingleResponse[list[PromotionOption]]` |
| PUT | `/campaigns/{id}/promotions` | `CAMPAIGNS_UPDATE` | `SingleResponse[CampaignDetail]` |

> `/campaigns/active` declarado ANTES de `/campaigns/{id}` (evita captura de ruta).

#### `POST /api/v1/marketing/campaigns` — `CAMPAIGNS_CREATE` → `201 SingleResponse[CampaignDetail]`

**Request** (`CampaignCreate`):
```json
{ "code": "verano_2026", "name": "Campaña Verano 2026", "description": "Descuentos de temporada",
  "start_date": "2026-12-01", "end_date": "2027-02-28", "target_vertical_id": "v1..." }
```

**Response 201** (`status='draft'`, `promotions_count=0`):
```json
{ "success": true, "data": {
  "id": "cmp1...", "code": "verano_2026", "name": "Campaña Verano 2026",
  "description": "Descuentos de temporada", "start_date": "2026-12-01", "end_date": "2027-02-28",
  "status": "draft", "target_vertical_id": "v1...", "target_vertical_name": "Dental",
  "promotions_count": 0, "active": true,
  "target_vertical": { "id": "v1...", "code": "dental", "name": "Dental" },
  "promotions": [],
  "created_on": "2026-06-08T15:00:00+00:00", "created_by": "u5...",
  "created_by_user": { "id": "u5...", "full_name": "Ana Torres", "email": "ana@medisage.pe" },
  "updated_on": "2026-06-08T15:00:00+00:00", "updated_by": "u5...", "updated_by_user": {"...":"..."}
} }
```

**Error 409** (`code` duplicado):
```json
{ "success": false, "detail": "Ya existe una campaña con el código 'verano_2026'", "code": "CAMPAIGN_CODE_TAKEN" }
```
**Error 400** (`end_date < start_date`):
```json
{ "success": false, "detail": "La fecha de fin no puede ser anterior a la de inicio", "code": "CAMPAIGN_INVALID_DATES" }
```
**Error 400** (vertical inexistente):
```json
{ "success": false, "detail": "La vertical objetivo no existe", "code": "TARGET_VERTICAL_NOT_FOUND" }
```

#### `POST /api/v1/marketing/campaigns/{id}/transition` — `CAMPAIGNS_UPDATE` → `SingleResponse[CampaignDetail]`

**Request** (`CampaignTransitionRequest`):
```json
{ "to_status": "active" }
```
**Error 400** (transición no permitida):
```json
{ "success": false, "detail": "Transición de campaña no permitida: de 'ended' a 'active'", "code": "CAMPAIGN_TRANSITION_NOT_ALLOWED" }
```

#### `GET /api/v1/marketing/campaigns/active` — `CAMPAIGNS_READ` → lista cruda `list[CampaignOption]`
```json
[ { "id": "cmp1...", "code": "verano_2026", "name": "Campaña Verano 2026", "status": "active" } ]
```

#### `PUT /api/v1/marketing/campaigns/{id}/promotions` — `CAMPAIGNS_UPDATE` → `SingleResponse[CampaignDetail]`

**Request** (`CampaignPromotionsReplace`, bulk-replace):
```json
{ "promotion_ids": ["prm1...", "prm2..."] }
```
**Error 404** (una promo no existe):
```json
{ "success": false, "detail": "Promoción no encontrada", "code": "PROMOTION_NOT_FOUND" }
```
**Error 404** (campaña) → `CAMPAIGN_NOT_FOUND`.

### Promotion (`routers/promotion.py`, prefix `/promotions`)

| Método | Ruta | Permiso | Response |
|---|---|---|---|
| POST | `/promotions/list` | `PROMOTIONS_READ` | `PaginatedResponse[PromotionItem]` |
| POST | `/promotions` (201) | `PROMOTIONS_CREATE` | `SingleResponse[PromotionDetail]` |
| GET | `/promotions/active` | `PROMOTIONS_READ` | lista cruda `list[PromotionOption]` |
| GET | `/promotions/{id}` | `PROMOTIONS_READ` | `SingleResponse[PromotionDetail]` |
| PUT | `/promotions/{id}` | `PROMOTIONS_UPDATE` | `SingleResponse[PromotionDetail]` |
| DELETE | `/promotions/{id}` (204) | `PROMOTIONS_DELETE` | — |
| GET | `/promotions/{id}/products` | `PROMOTIONS_READ` | `SingleResponse[list[ProductOption]]` |
| PUT | `/promotions/{id}/products` | `PROMOTIONS_UPDATE` | `SingleResponse[PromotionDetail]` |
| GET | `/promotions/{id}/usage-summary` | `PROMOTION_USAGES_READ` | `SingleResponse[PromotionUsageSummary]` |

#### `POST /api/v1/marketing/promotions` — `PROMOTIONS_CREATE` → `201 SingleResponse[PromotionDetail]`

**Request** (`PromotionCreate`, percentage):
```json
{ "code": "des_20", "name": "20% de descuento", "discount_type": "percentage",
  "discount_value": "20.00", "currency": "PEN", "start_date": "2026-12-01", "end_date": "2027-02-28",
  "max_uses_total": 100, "max_uses_per_person": 1, "applies_to_all_products": false }
```

**Response 201** (decimales como STRING):
```json
{ "success": true, "data": {
  "id": "prm1...", "code": "des_20", "name": "20% de descuento", "description": null,
  "discount_type": "percentage", "discount_value": "20.00", "currency": "PEN",
  "start_date": "2026-12-01", "end_date": "2027-02-28", "max_uses_total": 100,
  "max_uses_per_person": 1, "applies_to_all_products": false, "products_count": 0,
  "campaigns_count": 0, "active": true, "products": [], "campaigns": [], "total_uses": 0,
  "created_on": "...", "created_by": "u5...", "created_by_user": {"...":"..."},
  "updated_on": "...", "updated_by": "u5...", "updated_by_user": {"...":"..."}
} }
```

**Error 400** (rango inválido — percentage fuera de 0-100, o fixed ≤ 0):
```json
{ "success": false, "detail": "El porcentaje debe estar entre 0 y 100", "code": "PROMOTION_INVALID_DISCOUNT" }
```
**Error 409** (`code` duplicado) → `PROMOTION_CODE_TAKEN`. **Error 400** (fechas) → `PROMOTION_INVALID_DATES`.

#### `PUT /api/v1/marketing/promotions/{id}/products` — `PROMOTIONS_UPDATE` → `SingleResponse[PromotionDetail]`

**Request** (`PromotionProductsReplace`):
```json
{ "product_ids": ["prd1...", "prd2..."] }
```
**Error 404** (un producto no existe vivo) → `PRODUCT_NOT_FOUND`.

#### `GET /api/v1/marketing/promotions/{id}/usage-summary` — `PROMOTION_USAGES_READ` → `SingleResponse[PromotionUsageSummary]`
```json
{ "success": true, "data": {
  "promotion_id": "prm1...", "total_uses": 37,
  "total_original_amount": "5550.00", "total_discount_amount": "1110.00", "total_final_amount": "4440.00"
} }
```

### Validación / aplicación (`routers/promotion_usage.py`)

| Método | Ruta | Permiso | Response |
|---|---|---|---|
| POST | `/promotions/eligible-for` | `PROMOTION_VALIDATE` | `SingleResponse[list[PromotionEligibility]]` |
| POST | `/promotions/{id}/validate` | `PROMOTION_VALIDATE` | `SingleResponse[PromotionEligibility]` |
| POST | `/compute-price` | `PROMOTION_VALIDATE` | `SingleResponse[ComputePriceResponse]` |
| POST | `/promotion-usages` (201) | `PROMOTION_APPLY` | `SingleResponse[PromotionUsageDetail]` |
| POST | `/promotion-usages/list` | `PROMOTION_USAGES_READ` | `PaginatedResponse[PromotionUsageItem]` |

> `/promotions/eligible-for` (literal) ANTES de `/promotions/{id}/validate` en el orden de rutas.

#### `POST /api/v1/marketing/promotions/eligible-for` — `PROMOTION_VALIDATE` → `SingleResponse[list[PromotionEligibility]]`

**Request** (`PromotionEligibilityRequest`):
```json
{ "product_id": "prd1...", "person_id": "p1..." }
```
**Response** (decimales STRING; `reason` = code del primer motivo si no elegible):
```json
{ "success": true, "data": [
  { "promotion_id": "prm1...", "code": "des_20", "name": "20% de descuento", "is_eligible": true,
    "reason": null, "original_amount": "150.00", "discount_amount": "30.00", "final_amount": "120.00", "currency": "PEN" },
  { "promotion_id": "prm2...", "code": "des_50", "name": "50 soles menos", "is_eligible": false,
    "reason": "PROMOTION_PERSON_LIMIT_REACHED", "original_amount": "150.00", "discount_amount": "50.00", "final_amount": "100.00", "currency": "PEN" }
] }
```

#### `POST /api/v1/marketing/compute-price` — `PROMOTION_VALIDATE` → `SingleResponse[ComputePriceResponse]`

**Request** (`ComputePriceRequest`, con promo):
```json
{ "product_id": "prd1...", "person_id": "p1...", "promotion_id": "prm1..." }
```
**Response**:
```json
{ "success": true, "data": {
  "original_amount": "150.00", "discount_amount": "30.00", "final_amount": "120.00", "currency": "PEN",
  "promotion": { "id": "prm1...", "code": "des_20", "name": "20% de descuento", "discount_type": "percentage", "discount_value": "20.00", "currency": "PEN" }
} }
```
**Response** (sin promo → `promotion_id` null):
```json
{ "success": true, "data": { "original_amount": "150.00", "discount_amount": "0.00", "final_amount": "150.00", "currency": "PEN", "promotion": null } }
```

#### `POST /api/v1/marketing/promotion-usages` — `PROMOTION_APPLY` → `201 SingleResponse[PromotionUsageDetail]`

**Request** (`ApplyPromotionRequest`):
```json
{ "promotion_id": "prm1...", "person_id": "p1...", "product_id": "prd1...",
  "appointment_id": "appt1...", "campaign_id": "cmp1...", "notes": "Aplicado en recepción" }
```
**Response 201** (`PromotionUsageDetail`, snapshot, decimales STRING):
```json
{ "success": true, "data": {
  "id": "use1...", "promotion_id": "prm1...", "promotion_name": "20% de descuento",
  "person_id": "p1...", "person_name": "Lucía Fernández Soto", "product_id": "prd1...", "product_name": "Limpieza dental",
  "appointment_id": "appt1...", "campaign_id": "cmp1...", "campaign_name": "Campaña Verano 2026",
  "original_amount": "150.00", "discount_amount": "30.00", "final_amount": "120.00", "currency": "PEN",
  "notes": "Aplicado en recepción", "created_on": "...", "created_by": "u5...", "created_by_user": {"...":"..."}
} }
```

**Errores de `apply`** (uno por paso):
```json
{ "success": false, "detail": "Promoción no encontrada", "code": "PROMOTION_NOT_FOUND" }
{ "success": false, "detail": "La promoción no está activa", "code": "PROMOTION_NOT_ACTIVE" }
{ "success": false, "detail": "La promoción está fuera de vigencia", "code": "PROMOTION_EXPIRED" }
{ "success": false, "detail": "Producto no encontrado", "code": "PRODUCT_NOT_FOUND" }
{ "success": false, "detail": "Persona no encontrada", "code": "PERSON_NOT_FOUND" }
{ "success": false, "detail": "La promoción no cubre este producto", "code": "PROMOTION_PRODUCT_NOT_COVERED" }
{ "success": false, "detail": "Ya se aplicó una promoción a esta cita", "code": "PROMOTION_ALREADY_APPLIED" }
{ "success": false, "detail": "La promoción alcanzó su límite de usos", "code": "PROMOTION_LIMIT_REACHED" }
{ "success": false, "detail": "La persona alcanzó su límite de usos de la promoción", "code": "PROMOTION_PERSON_LIMIT_REACHED" }
```

## Routers — ejemplos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; `actor: CurrentAuth` aparte cuando se necesita el id para audit; `/active` antes de `/{id}`.

```python
# routers/campaign.py (extracto)
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.marketing.schemas.campaign import (
    CampaignCreate, CampaignDetail, CampaignItem, CampaignOption,
    CampaignPromotionsReplace, CampaignTransitionRequest, CampaignUpdate,
)
from app.modules.marketing.schemas.promotion import PromotionOption
from app.modules.marketing.services import campaign as campaign_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/campaigns", tags=["marketing · campaigns"])

CampaignIdPath = Annotated[str, Path(min_length=1, description="Campaign UUID")]


@router.post("/list", response_model=PaginatedResponse[CampaignItem],
             dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))])
async def list_campaigns(query: QueryRequest, db: DBSession) -> PaginatedResponse[CampaignItem]:
    return await campaign_service.list_paginated(db, query)


@router.post("", response_model=SingleResponse[CampaignDetail], status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(RequirePermission("CAMPAIGNS_CREATE"))])
async def create_campaign(payload: CampaignCreate, db: DBSession, actor: CurrentAuth) -> SingleResponse[CampaignDetail]:
    return await campaign_service.create(db, payload, actor_id=actor.id)


@router.get("/active", response_model=list[CampaignOption],
            dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))])
async def list_active_campaigns(db: DBSession) -> list[CampaignOption]:
    return await campaign_service.list_active(db)  # lista cruda, sin envelope


@router.get("/{campaign_id}", response_model=SingleResponse[CampaignDetail],
            dependencies=[Depends(RequirePermission("CAMPAIGNS_READ"))])
async def get_campaign(campaign_id: CampaignIdPath, db: DBSession) -> SingleResponse[CampaignDetail]:
    return await campaign_service.get_by_id(db, campaign_id)


@router.post("/{campaign_id}/transition", response_model=SingleResponse[CampaignDetail],
             dependencies=[Depends(RequirePermission("CAMPAIGNS_UPDATE"))])
async def transition_campaign(campaign_id: CampaignIdPath, payload: CampaignTransitionRequest,
                              db: DBSession, actor: CurrentAuth) -> SingleResponse[CampaignDetail]:
    return await campaign_service.transition(db, campaign_id, payload.to_status, actor_id=actor.id)


@router.put("/{campaign_id}/promotions", response_model=SingleResponse[CampaignDetail],
            dependencies=[Depends(RequirePermission("CAMPAIGNS_UPDATE"))])
async def set_campaign_promotions(campaign_id: CampaignIdPath, payload: CampaignPromotionsReplace,
                                  db: DBSession, actor: CurrentAuth) -> SingleResponse[CampaignDetail]:
    return await campaign_service.set_promotions(db, campaign_id, payload.promotion_ids, actor_id=actor.id)
```

```python
# routers/promotion_usage.py (extracto) — apply + validación
router = APIRouter(tags=["marketing · promotion usage"])  # sin prefix; paths absolutos abajo

@router.post("/promotions/eligible-for", response_model=SingleResponse[list[PromotionEligibility]],
             dependencies=[Depends(RequirePermission("PROMOTION_VALIDATE"))])
async def eligible_for(payload: PromotionEligibilityRequest, db: DBSession) -> SingleResponse[list[PromotionEligibility]]:
    return await usage_service.eligible_for(db, product_id=payload.product_id, person_id=payload.person_id)


@router.post("/promotion-usages", response_model=SingleResponse[PromotionUsageDetail], status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(RequirePermission("PROMOTION_APPLY"))])
async def apply_promotion(payload: ApplyPromotionRequest, db: DBSession, actor: CurrentAuth) -> SingleResponse[PromotionUsageDetail]:
    return await usage_service.apply(
        db, promotion_id=payload.promotion_id, person_id=payload.person_id,
        product_id=payload.product_id, appointment_id=payload.appointment_id,
        campaign_id=payload.campaign_id, notes=payload.notes, actor_id=actor.id)
```

> `/promotions/eligible-for` y `/promotions/{id}/validate` viven en `promotion_usage.py` (agrupados por `PROMOTION_VALIDATE`); `/promotions/{id}/products` y `/promotions/{id}/usage-summary` viven en `promotion.py`. El aggregator incluye `promotion_router` antes que `promotion_usage_router`; ambos cuelgan de `/promotions/...` pero los paths son inequívocos (literal `eligible-for` no es un UUID; `/{id}/validate` y `/{id}/products` son segmentos literales distintos).

## Catálogo de error codes

| code | HTTP | Excepción | Dónde |
|---|---|---|---|
| `CAMPAIGN_NOT_FOUND` | 404 | NotFound | campaign get/update/transition/remove/set_promotions |
| `CAMPAIGN_CODE_TAKEN` | 409 | AlreadyExists | campaign create (code único) |
| `CAMPAIGN_INVALID_DATES` | 400 | BadRequest | campaign create/update (end < start) |
| `TARGET_VERTICAL_NOT_FOUND` | 400 | BadRequest | campaign create/update (vertical inexistente) |
| `CAMPAIGN_TRANSITION_NOT_ALLOWED` | 400 | BadRequest | campaign transition (matriz) |
| `PROMOTION_NOT_FOUND` | 404 | NotFound | promotion get/update/.../ set_promotions / apply paso 1 |
| `PROMOTION_CODE_TAKEN` | 409 | AlreadyExists | promotion create (code único) |
| `PROMOTION_INVALID_DISCOUNT` | 400 | BadRequest | `_validate_discount` (create/update) |
| `PROMOTION_INVALID_DATES` | 400 | BadRequest | promotion create/update |
| `PRODUCT_NOT_FOUND` | 404 | NotFound | set_products / apply paso 3 / compute |
| `PERSON_NOT_FOUND` | 404 | NotFound | apply paso 4 / compute |
| `PROMOTION_PRODUCT_NOT_COVERED` | 400 | BadRequest | apply paso 5 |
| `PROMOTION_ALREADY_APPLIED` | 409 | Conflict | apply paso 6 (no-stacking) |
| `PROMOTION_NOT_ACTIVE` | 400 | BadRequest | apply paso 2 |
| `PROMOTION_EXPIRED` | 400 | BadRequest | apply paso 2 |
| `PROMOTION_LIMIT_REACHED` | 400 | BadRequest | apply paso 7 |
| `PROMOTION_PERSON_LIMIT_REACHED` | 400 | BadRequest | apply paso 8 |
| `APPOINTMENT_NOT_FOUND` | 404 | NotFound | apply: `appointment_id` provisto pero inexistente/borrado (evita el 500 del FK) |
| `CAMPAIGN_NOT_FOUND` | 404 | NotFound | apply: `campaign_id` provisto pero inexistente/borrado (evita el 500 del FK) |

> **Orden de validación de `apply`** (review F3): promo → **vigencia** (activa/fechas) → producto → persona → cita (existe + no-stacking) → campaña (existe) → cobertura/límites → snapshot. La vigencia se chequea ANTES de la existencia de producto/persona (precedencia del contrato). `APPOINTMENT_NOT_FOUND`/`CAMPAIGN_NOT_FOUND` son adiciones defensivas (los `appointment_id`/`campaign_id` son FK reales nullables; un id type-válido inexistente debe dar 404, no 500 — lección "los services nunca 500 con input type-válido").

## Migrations

Migraciones **manuales y numeradas** (convención medisage). `marketing` arranca en `0022` (la última aplicada antes = `0021_scheduling_appointment`). **Revision id ≤ 32 chars** (alembic_version VARCHAR(32)). Las FKs cross-módulo de `marketing` SON reales (las tablas existen). La migración `0022` además **CIERRA las 3 FKs forward de ADR-009** con `create_foreign_key` aditivo.

**Cadena de revids** (las 3 ≤32): `0022_marketing_campaign` (23) → `0023_marketing_promotion` (25) → `0024_marketing_promotion_usage` (30).

### `0022_marketing_campaign.py` (F1 — campaign + cierre FKs forward) · revid `0022_marketing_campaign` (23 chars) · down_revision `0021_scheduling_appointment`

```sql
CREATE TABLE campaign (
    id                 VARCHAR(36) PRIMARY KEY,
    code               VARCHAR(40)  NOT NULL UNIQUE,
    name               VARCHAR(120) NOT NULL,
    description        VARCHAR(500),
    start_date         DATE NOT NULL,
    end_date           DATE,
    status             VARCHAR(20)  NOT NULL DEFAULT 'draft',
    target_vertical_id VARCHAR(36) REFERENCES vertical(id),     -- FK REAL a catalog
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at         TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE UNIQUE INDEX uq_campaign_code           ON campaign (code);
CREATE INDEX        ix_campaign_target_vertical ON campaign (target_vertical_id);
CREATE INDEX        ix_campaign_status          ON campaign (status);

-- Cierre de las 3 FKs forward (ADR-009). campaign YA existe en esta migración.
-- Los índices de estas columnas YA existen (creados por crm/conversations) → NO recrearlos.
-- Seguro hoy: todos los valores son NULL.
ALTER TABLE person_lead_status    ADD CONSTRAINT fk_person_lead_status_campaign    FOREIGN KEY (source_campaign_id)  REFERENCES campaign(id);
ALTER TABLE lead_status_history   ADD CONSTRAINT fk_lead_status_history_campaign   FOREIGN KEY (source_campaign_id)  REFERENCES campaign(id);
ALTER TABLE channel_account       ADD CONSTRAINT fk_channel_account_campaign       FOREIGN KEY (default_campaign_id) REFERENCES campaign(id);
-- revision = "0022_marketing_campaign"
-- down_revision = "0021_scheduling_appointment"
```

```python
# upgrade() en alembic (op.*)
op.create_table("campaign", ...)  # cols + active server_default=sa.text("true")
op.create_index("uq_campaign_code", "campaign", ["code"], unique=True)
op.create_index("ix_campaign_target_vertical", "campaign", ["target_vertical_id"])
op.create_index("ix_campaign_status", "campaign", ["status"])
op.create_foreign_key("fk_person_lead_status_campaign", "person_lead_status", "campaign", ["source_campaign_id"], ["id"])
op.create_foreign_key("fk_lead_status_history_campaign", "lead_status_history", "campaign", ["source_campaign_id"], ["id"])
op.create_foreign_key("fk_channel_account_campaign", "channel_account", "campaign", ["default_campaign_id"], ["id"])

# downgrade() — dropear los 3 FK ANTES de drop_table campaign.
op.drop_constraint("fk_channel_account_campaign", "channel_account", type_="foreignkey")
op.drop_constraint("fk_lead_status_history_campaign", "lead_status_history", type_="foreignkey")
op.drop_constraint("fk_person_lead_status_campaign", "person_lead_status", type_="foreignkey")
op.drop_table("campaign")
```

> ⚠ **Nombres de índice forward inconsistentes** (gotcha §13): `ix_person_lead_status_campaign` (nombre a mano) vs `ix_lead_status_history_source_campaign_id` / `ix_channel_account_default_campaign_id` (autogenerados). Al ALTER, **NO tocar los índices** (ya existen) — solo `create_foreign_key`.

### `0023_marketing_promotion.py` (F2 — promotion + M:N) · revid `0023_marketing_promotion` (25 chars) · down_revision `0022_marketing_campaign`

```sql
CREATE TABLE promotion (
    id                      VARCHAR(36) PRIMARY KEY,
    code                    VARCHAR(40)  NOT NULL UNIQUE,
    name                    VARCHAR(120) NOT NULL,
    description             VARCHAR(500),
    discount_type           VARCHAR(20)  NOT NULL,
    discount_value          NUMERIC(10,2) NOT NULL,
    currency                VARCHAR(3)   NOT NULL DEFAULT 'PEN',
    start_date              DATE NOT NULL,
    end_date                DATE,
    max_uses_total          INTEGER,
    max_uses_per_person     INTEGER,
    applies_to_all_products BOOLEAN NOT NULL DEFAULT FALSE,
    active                  BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE UNIQUE INDEX uq_promotion_code ON promotion (code);

CREATE TABLE campaign_promotion (   -- M:N, PK compuesta, FK CASCADE
    campaign_id  VARCHAR(36) NOT NULL REFERENCES campaign(id)  ON DELETE CASCADE,
    promotion_id VARCHAR(36) NOT NULL REFERENCES promotion(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, promotion_id)
);

CREATE TABLE promotion_product (    -- M:N, FK a promotion + product CASCADE
    promotion_id VARCHAR(36) NOT NULL REFERENCES promotion(id) ON DELETE CASCADE,
    product_id   VARCHAR(36) NOT NULL REFERENCES product(id)   ON DELETE CASCADE,
    PRIMARY KEY (promotion_id, product_id)
);
-- revision = "0023_marketing_promotion"
-- down_revision = "0022_marketing_campaign"
```

### `0024_marketing_promotion_usage.py` (F3 — promotion_usage + UNIQUE parcial) · revid `0024_marketing_promotion_usage` (30 chars) · down_revision `0023_marketing_promotion`

```sql
CREATE TABLE promotion_usage (      -- SIN deleted_at (audit inmutable)
    id              VARCHAR(36) PRIMARY KEY,
    promotion_id    VARCHAR(36) NOT NULL REFERENCES promotion(id),
    person_id       VARCHAR(36) NOT NULL REFERENCES person(id),
    product_id      VARCHAR(36) NOT NULL REFERENCES product(id),
    appointment_id  VARCHAR(36) REFERENCES appointment(id),     -- NULL = sin cita
    campaign_id     VARCHAR(36) REFERENCES campaign(id),        -- NULL = sin campaña
    original_amount NUMERIC(10,2) NOT NULL,
    discount_amount NUMERIC(10,2) NOT NULL,
    final_amount    NUMERIC(10,2) NOT NULL,
    currency        VARCHAR(3) NOT NULL,
    notes           VARCHAR(500),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_on TIMESTAMPTZ NOT NULL, created_by VARCHAR(36) NOT NULL,
    updated_on TIMESTAMPTZ NOT NULL, updated_by VARCHAR(36) NOT NULL
);
CREATE INDEX ix_promotion_usage_promotion   ON promotion_usage (promotion_id);
CREATE INDEX ix_promotion_usage_person      ON promotion_usage (person_id);
CREATE INDEX ix_promotion_usage_product     ON promotion_usage (product_id);
CREATE INDEX ix_promotion_usage_appointment ON promotion_usage (appointment_id);
CREATE INDEX ix_promotion_usage_campaign    ON promotion_usage (campaign_id);
CREATE INDEX ix_promotion_usage_created_on  ON promotion_usage (created_on);
-- NO stacking: UNIQUE PARCIAL (una promo por cita). SIN cláusula deleted_at (no hay SoftDelete).
CREATE UNIQUE INDEX uq_promotion_usage_appointment
    ON promotion_usage (appointment_id) WHERE appointment_id IS NOT NULL;
-- revision = "0024_marketing_promotion_usage"
-- down_revision = "0023_marketing_promotion"
```

```python
# El índice parcial en la migración Postgres:
op.create_index(
    "uq_promotion_usage_appointment", "promotion_usage", ["appointment_id"],
    unique=True, postgresql_where=sa.text("appointment_id IS NOT NULL"))
# En el modelo ORM va con postgresql_where + sqlite_where (para el smoke en aiosqlite).
```

> F0 y F4 NO llevan migración (F0 = solo seed/skeleton; F4 = integración cross-módulo sobre tablas ya creadas).

## Integración cross-módulo (F4 — sin migración nueva)

### 1) `scheduling`: `apply_promotion_id` atómico

`AppointmentCreate` gana un campo opcional; `create_appointment` lo aplica en la MISMA sesión (atómico, sin commit intermedio).

```python
# scheduling/schemas/appointment.py — AppointmentCreate += un campo:
class AppointmentCreate(BaseModel):
    # ... campos existentes ...
    apply_promotion_id: str | None = None  # NUEVO (F4): aplica una promo a la cita recién creada


# scheduling/services/appointment.py — en create_appointment, ANTES del return final
# (tras db.add(appt); await db.flush() y el flush del history):
if payload.apply_promotion_id:
    await marketing_promotion_usage_service.apply(
        db, promotion_id=payload.apply_promotion_id, person_id=payload.person_id,
        product_id=payload.product_id, appointment_id=appt.id, actor_id=actor_id)
# Atómico: apply lanza excepciones de DOMINIO (PROMOTION_*) → el rollback global del
# request REVIERTE la cita si la promo es inválida. db.flush() (NO commit).
```

> **Dirección del import**: `scheduling` → `marketing` (OK). `marketing` NO importa `scheduling` a nivel módulo (su FK `appointment_id` es column, sin relationship). **Reschedule**: la cita nueva NO re-aplica la promo (quedó en la cita vieja); documentado — el usuario re-aplica si quiere. La firma de `marketing.promotion_usage.apply` DEBE estar estable ANTES de tocar scheduling (§13).

### 2) `bots`: tool `list_eligible_promotions` + `book_appointment` extendido + seed

```python
# bots/services/engine/tools/marketing.py (NUEVO) — read-only
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainException
from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.marketing.services import promotion_usage as mkt_usage


@register_tool("list_eligible_promotions")
async def list_eligible_promotions(args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession) -> dict[str, Any]:
    """Lista las promos elegibles para (product_id de args, person de ctx). Read-only.
    Anti-IDOR: usa ctx.person_id como sujeto (NO un person_id del LLM). Guard si None."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    try:
        resp = await mkt_usage.eligible_for(db, product_id=args["product_id"], person_id=ctx.person_id)
        return {"ok": True, "promotions": [e.model_dump(mode="json") for e in resp.data if e.is_eligible]}
    except DomainException as exc:  # solo dominio → reportar al LLM, no romper el turno
        return {"ok": False, "error": getattr(exc, "code", None) or str(exc)[:255]}
```

```python
# bots/services/engine/tools/scheduling.py — book_appointment: leer apply_promotion_id
@register_tool("book_appointment")
async def book_appointment(args, ctx, db):
    try:
        result = await sched_bot.book_from_bot(
            db, ctx, doctor_id=args["doctor_id"], office_id=args["office_id"],
            product_id=args["product_id"], scheduled_for=datetime.fromisoformat(args["scheduled_for"]),
            person_id=args.get("person_id"),
            apply_promotion_id=args.get("apply_promotion_id"))  # NUEVO (F4)
        return {"ok": True, "appointment_id": result.data.id}
    except DomainException as exc:  # captura TAMBIÉN las excepciones de dominio de marketing
        return {"ok": False, "error": getattr(exc, "code", None) or str(exc)[:255]}
```

> `book_from_bot` gana el kwarg `apply_promotion_id: str | None = None` y lo pasa al `AppointmentCreate`. `import app.modules.bots.services.engine.tools.marketing` al final de `tools/__init__.py` (o se registra el `@register_tool`). **seed**: 4ª tupla en `BOT_TOOL_SEED` (`"list_eligible_promotions"`, `requires_confirmation=False`, `target_service="marketing.promotion_usage.eligible_for"`) + extender el `parameters_schema` de `book_appointment` con `apply_promotion_id` opcional.

> **Pre-requisito (§13)**: la firma de `marketing.promotion_usage.apply`/`eligible_for` DEBE existir y estar estable ANTES de tocar bots (el import de tools al boot dispara `@register_tool`; un `ImportError` tumba el arranque). → **F4 va DESPUÉS de F3** (marketing services ya escritos).

## Seed — permisos (F0)

Los **12 permisos** de `marketing` (`module="MARKETING"`) se agregan a `app/core/seed.py:SEED_PERMISSIONS`:

```
MENU-MARKETING, CAMPAIGNS_READ, CAMPAIGNS_CREATE, CAMPAIGNS_UPDATE, CAMPAIGNS_DELETE,
PROMOTIONS_READ, PROMOTIONS_CREATE, PROMOTIONS_UPDATE, PROMOTIONS_DELETE,
PROMOTION_VALIDATE, PROMOTION_APPLY, PROMOTION_USAGES_READ
```

- **ADMIN**: los 12.
- **ASESOR**: ya **forward-declara 6** (`MENU-MARKETING`, `CAMPAIGNS_READ`, `PROMOTIONS_READ`, `PROMOTION_VALIDATE`, `PROMOTION_APPLY`, `PROMOTION_USAGES_READ`) en el set `ASESOR_PERMISSION_CODES` → se auto-activan al crear las filas en F0.
- **DOCTOR**: ninguno.

> ⚠ Los 6 codes de ASESOR HOY solo viven en el `set` `ASESOR_PERMISSION_CODES`, **NO** en `SEED_PERMISSIONS` (no existen como filas). F0 los crea. **No hay seed de datos de dominio** (no hay catálogo de estado configurable; `Campaign.status` es enum fijo) — a diferencia de scheduling/crm, marketing NO seedea estados ni matriz.

## Checklist de implementación (mapeado a fases F0–F4)

### F0 — Prep (sin migración; solo seed + skeleton + frontend espejo)
- [ ] Agregar los 12 permisos `MARKETING` a `app/core/seed.py:SEED_PERMISSIONS`. ADMIN = 12; ASESOR = 6 (ya forward-declarados); DOCTOR = 0.
- [ ] Skeleton inerte `backend/app/modules/marketing/{models,schemas,repositories,services,routers}/__init__.py` (solo docstring; **NO registrado** en `modules/__init__.py`/`main.py` todavía) + `enums.py` (`CampaignStatus`, `DiscountType`).
- [ ] (Frontend F0) nav grupo "Marketing" (`MENU-MARKETING`) + iconMap (`MegaphoneRegular`/`TagRegular`/`ReceiptRegular`, verificar que existan en `@fluentui/react-icons`); `endpoints.ts` (bloque MARKETING); `types/marketing.types.ts` (espejo completo, decimales `string`); skeleton inerte — ver [`frontend.md`](frontend.md).
- [ ] QA/PROD RO: login admin → el JWT contiene los 12 permisos MARKETING; rutas `/api/v1/marketing/*` → 404 (módulo no registrado).

### F1 — Campaign (migración `0022_marketing_campaign` + cierre FKs forward)
- [ ] `models/campaign.py` (**SUBSET F1: sin `promotions` relationship**) + `models/associations.py` + `models/__init__.py` (importa SOLO `Campaign`).
- [ ] Migración `0022_marketing_campaign` (`down_revision="0021_scheduling_appointment"`): `create_table('campaign')` + índices + **`create_foreign_key` ×3 (cierre ADR-009)**.
- [ ] `schemas/campaign.py` (`CampaignOption`/`Item`/`Detail`/`Create`/`Update`/`TransitionRequest`/`PromotionsReplace`; `CampaignDetail.promotions` declarado, devuelto `[]`).
- [ ] `repositories/campaign.py` (`get_by_code`/`list_active`/`get_by_ids`/`campaign_name_map`).
- [ ] `services/campaign.py` (CRUD + `transition` matriz hardcodeada + `list_active`; `promotions_count`=0; `set_promotions`/`get_promotions` POSPUESTOS a F2).
- [ ] `routers/campaign.py` (CRUD + `/active` + `/{id}/transition`). **Registrar el módulo** (`modules/__init__.py` + `main.py` + aggregator).
- [ ] (Frontend F1) `/marketing/campanas` (tabla + drawer Datos/Auditoría; badge status; "Cambiar estado") — ver [`ui.md`](ui.md).
- [ ] Test: `CAMPAIGN_CODE_TAKEN` (409), `CAMPAIGN_INVALID_DATES` (400), `TARGET_VERTICAL_NOT_FOUND` (400), `CAMPAIGN_TRANSITION_NOT_ALLOWED` (400 — `ended→active`); transición válida `draft→active`. QA E2E: las 3 FK forward existen (insertar `person_lead_status.source_campaign_id` con un id inválido → 23503).

### F2 — Promotion (migración `0023_marketing_promotion`)
- [ ] `models/promotion.py` + **agregar `promotions` relationship a `Campaign`** + `models/__init__.py` (importa `Promotion`).
- [ ] Migración `0023_marketing_promotion` (`create_table('promotion')` + `campaign_promotion` + `promotion_product`).
- [ ] `schemas/promotion.py` (`PromotionOption`/`Item`/`Detail`/`Create`/`Update`/`ProductsReplace`).
- [ ] `repositories/promotion.py` (`get_by_code`/`list_active`/`get_by_ids`/`get_for_update`/`promotion_name_map`) + `campaign_promotion.py` + `promotion_product.py` (join propio).
- [ ] `services/promotion.py` (CRUD + `_validate_discount` + `set_products`/`get_products` + `usage_summary` [0 hasta F3]) + activar `campaign.set_promotions`/`get_promotions` + `promotions_count`.
- [ ] `routers/promotion.py` (CRUD + `/active` + `/{id}/products` + `/{id}/usage-summary`).
- [ ] (Frontend F2) `/marketing/promociones` (drawer form discriminado por `discount_type`; M:N productos/campañas) — ver [`ui.md`](ui.md).
- [ ] Test: `PROMOTION_INVALID_DISCOUNT` (percentage>100, fixed≤0; en create Y update), `PROMOTION_CODE_TAKEN` (409), `PROMOTION_INVALID_DATES`, `PRODUCT_NOT_FOUND` (set_products); `discount_type` inmutable en update; M:N bulk-replace; `products_count`/`campaigns_count`/`promotions_count`.

### F3 — PromotionUsage + apply/validación (migración `0024_marketing_promotion_usage`)
- [ ] `models/promotion_usage.py` (SIN SoftDelete; UNIQUE parcial `postgresql_where`+`sqlite_where`) + `models/__init__.py` (importa `PromotionUsage`).
- [ ] Migración `0024_marketing_promotion_usage` (FKs reales + 6 índices + UNIQUE parcial).
- [ ] `schemas/promotion_usage.py` (`Item`/`Detail` + `Apply`/`Eligibility`/`ComputePrice`/`Summary`).
- [ ] `repositories/promotion_usage.py` (`get_by_appointment`/`count_for_promotion[_person]`/`usage_summary`).
- [ ] `services/promotion_usage.py` (`apply` 10 pasos + `_compute_discount` + `eligible_for`/`validate`/`compute_price` + `list_paginated`).
- [ ] `routers/promotion_usage.py` (`/eligible-for`, `/{id}/validate`, `/compute-price`, `/promotion-usages`[`/list`]).
- [ ] (Frontend F3) `/marketing/usos` (read-only DataTable, decimales formateados con currency) — ver [`ui.md`](ui.md).
- [ ] Test: cada code de `apply` (paso 1-8); `_compute_discount` (percentage cap a base_price, fixed `min(value, base_price)`, ROUND_HALF_UP); no-stacking (`PROMOTION_ALREADY_APPLIED` 409 + UNIQUE parcial backstop con 2 applies a la misma cita); `eligible_for`/`validate`/`compute_price` (dry-run, `reason` = code); `usage_summary` (sums).

### F4 — Integración (sin migración)
- [ ] `scheduling`: `AppointmentCreate += apply_promotion_id` + llamada atómica a `marketing.promotion_usage.apply` en `create_appointment` (db.flush, sin commit). `book_from_bot += apply_promotion_id`.
- [ ] `bots`: `tools/marketing.py` (`@register_tool("list_eligible_promotions")`, read-only, anti-IDOR `ctx.person_id`) + import en `tools/__init__.py` + `book_appointment` lee `apply_promotion_id` + seed `BotTool` (4ª tupla + `parameters_schema` extendido).
- [ ] Test: book con `apply_promotion_id` válido → cita + usage (mismo tx); book con promo inválida → rollback (NI cita NI usage); `list_eligible_promotions` con `ctx.person_id=None` → `no_person`; la tool pasa de `is_registered=false` a operativa.

Cada fase: backend e2e + smoke (sqlite, RESULT=PASS+conteo a stdout) → frontend e2e (tsc+build+prettier) → **review adversaria Workflow 4 dims + verificación por hallazgo (chequear `raw==confirmed+refuted+null`)** → commit limpio sin Co-Authored-By → ff develop→qa → **gate AskUserQuestion (separado del merge)** → prod → QA E2E real + PROD RO → actualizar memoria.

## Gotchas críticos (del mapeo — para que el deploy no rompa)

- **NO modificar `catalog`/`crm`/`conversations` en código** (solo F1 ALTER en migración additive). marketing LEE vía `product_repository.get_by_id` (single), join propio para el M:N de productos, `vertical_repository.get_by_ids`, `person_option_map`. F4 SÍ toca `scheduling`+`bots` (aprobado).
- **`appointment.id`, `person.id`, `product.id`, `vertical.id`, `campaign.id` = `String(36)`** → todas las FK de marketing = `String(36)`.
- **`base_price` = `Decimal` `Numeric(10,2)`**, serializa STRING. Aritmética en `Decimal` `ROUND_HALF_UP`, descuento **cap a base_price** (`min(discount, base_price)`).
- **El service NO commitea** (`get_db` lo hace). `apply` en `create_appointment` = atómico por construcción; usar `db.flush()`. Si `apply` lanza, el rollback global revierte la cita.
- **`find_by_identifier_or_create(... *, campaign_id=None)`**: NO cambiar su firma. Marketing solo cierra la FK de la columna `source_campaign_id`.
- **Nombres de índice de las FK forward son inconsistentes** (`ix_person_lead_status_campaign` a mano vs `ix_lead_status_history_source_campaign_id` / `ix_channel_account_default_campaign_id` autogenerados) → al ALTER, NO tocar los índices (ya existen), solo `create_foreign_key`.
- **`Campaign.status` NO es catálogo configurable**: es enum fijo, matriz hardcodeada en el service (NO una tabla `*_transition`, NO un endpoint `/{id}/transitions`). Diverge de crm/scheduling a propósito (decisión #2).
- **Tool del bot**: el `code` es la KEY de `TOOL_REGISTRY` + el name del LLM + el code de `BotTool` (los 3 iguales). Firma EXACTA `async def fn(args: dict, ctx: BotInvocationContext, db: AsyncSession) -> dict`. `ctx.person_id` (puede ser None → guard `no_person`). Anti-IDOR: usar `ctx.person_id`, NO un `person_id` del LLM. Capturar solo `DomainException`. Import en `tools/__init__.py` o no se registra.
- **UNIQUE parcial dialect-agnóstico**: `postgresql_where` + `sqlite_where` en el modelo (lección crm F1) para que el smoke en aiosqlite también lo respete. SIN cláusula `deleted_at` (promotion_usage no tiene SoftDelete).
- **Smoke (create_all) NO caza**: drift TS↔Pydantic, bugs de render, IDOR, estado-preexistente, bugs solo-migración (revision id largo, el ALTER de cierre de FK forward — el smoke usa `create_all`, no las migraciones). Lo caza la review adversaria + el QA E2E real (que SÍ corre las migraciones contra Postgres).
- **revision id ≤ 32 chars**: `0022_marketing_campaign` (23), `0023_marketing_promotion` (25), `0024_marketing_promotion_usage` (30) → OK.

Molde global = **crm** (catálogo `code` UNIQUE + denormalización batch + M:N + estados con flags) + **scheduling** (matriz de transición hardcodeada en el service, `apply` atómico cross-módulo, migraciones manuales con cierre de FK forward, bot facade/tools). Lecciones operativas transversales [[feedback-medisage-operational-lessons]]: Decimal en el wire = string; el smoke NO caza drift TS↔Pydantic ni bugs de migración — la review adversaria + el QA E2E sí; verificar que el verificador CORRIÓ (RESULT=PASS + conteo); 1 comando por tool-call; gate de prod = AskUserQuestion separado del merge; toda tool del bot que recibe un id necesita guard de pertenencia (anti-IDOR); seed idempotente respeta la parcialidad del UNIQUE.
