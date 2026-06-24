# Módulo `dashboards` — Backend deep-dive

> **Última actualización**: 2026-06-24
> **Audiencia**: developer implementando `backend/app/modules/dashboards/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview), [`design.md`](design.md) (arquitectura + cómputo del embudo + roadmap), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`ADR-015`](../../decisions/ADR-015-dashboards-materialized-aggregation.md) (la decisión: módulo read-only + rollup materializado + job + reportes server-side + Fluent Charts), y los ADRs **reutilizados**: [`ADR-008`](../../decisions/ADR-008-configurable-status-transition-matrix.md) (estados configurables → resolver por `code`/flags, nunca por id hardcodeado), [`ADR-009`](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (FK lógica `branch_id` sin constraint), [`ADR-011`](../../decisions/ADR-011-firestore-message-stream-cqrs.md) (mensajes en Firestore → no agregables en SQL), [`ADR-012`](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md) (shared-secret + dispatch async → molde del refresh), [`ADR-013`](../../decisions/ADR-013-marketing-campaign-status-and-atomic-apply.md) (`usage_summary` = molde del endpoint de métrica agregada). Deep-dives molde: [`../marketing/backend.md`](../marketing/backend.md) (`usage_summary` = `SUM/COALESCE/group_by`) y [`../calendar/backend.md`](../calendar/backend.md) (estructura de la ficha).

> **Contrato autoritativo**: este doc respeta la **spec compartida** de `dashboards`. Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** (y por encima, el código real ya mapeado) y hay que corregir este doc.

> **Convenciones heredadas de los 9 módulos shipped** (repetidas para que el doc se lea solo):
>
> 1. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `BadRequestException`, `ForbiddenException`, `UnauthorizedException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` whitelist estricta (denormalizados NO server-sortable/filterable — lección `cd10c78`).
> 2. **`detail` de dominio en español, `code` en inglés**; mensajes de validators Pydantic en inglés (el front re-valida con Zod). UI 100% español.
> 3. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), error `{success:false, detail, code?, errors?}`. **Este módulo NO pagina** — todas las lecturas son `SingleResponse[X]` (molde `marketing.usage_summary` = `SingleResponse[PromotionUsageSummary]`).
> 4. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `dashboards` arranca en `0026` (`down_revision="0025_calendar_connection"`, la última aplicada — `calendar` fue el módulo #9).
> 5. **`Decimal`/`Numeric` serializa como STRING en el wire** (Pydantic v2 + `model_config`); `value` monetario nullable → **`COALESCE` en el `SUM`**.
> 6. **TZ**: `metric_date` es la frontera **UTC** del día; los datetimes que viajan (`last_refreshed_at`, `refreshed_at`) son `timestamptz` UTC ISO 8601 con offset; el render local lo hace el front.

`dashboards` es el **módulo #10** de medisage (tras los 8 de dominio + `calendar` #9). Es un módulo **read-only / de agregación**: **no crea entidades de negocio**, no muta ni una fila de los otros módulos, no toca `compute_available_slots`. Su única persistencia es una **capa de agregación materializada** (`dashboard_daily_metric`, un *daily rollup*) + un singleton de observabilidad (`dashboard_refresh_state`). Cierra **OE3 + HU26/HU27 + RNF-05** y reemplaza las figuras falsas del Cap.6. Depende de `crm` (`lead_status_history`, `lead_status`, `person`, `person_customer_status`), `scheduling` (`appointment`, `appointment_status`), `conversations` (`conversation`), `bots` (`bot_event`), `clinic` (`branch` — filtro/meta) y `admin` (RBAC). Reutiliza `app.core.config.Settings`, el shared-secret de `bots` (ADR-012) y los catálogos de estado sembrados (ADR-008).

## Estructura de archivos a crear

```
backend/app/modules/dashboards/
├── __init__.py
├── enums.py                            # DashboardMetric (StrEnum, code-level) + ReportFormat
├── models/
│   ├── __init__.py                     # importa los modelos (registro en Base.metadata)
│   ├── dashboard_daily_metric.py       # rollup / fact table
│   └── dashboard_refresh_state.py      # singleton de observabilidad
├── schemas/
│   ├── __init__.py
│   ├── filter.py                       # DashboardFilter (request body común) + validación de rango
│   ├── funnel.py                       # FunnelStage + FunnelSummary
│   ├── series.py                       # TimeSeriesPoint + TimeSeries
│   ├── distribution.py                 # DistributionBucket + DistributionSummary
│   ├── summary.py                      # KpiSummary
│   ├── meta.py                         # DashboardMeta (+ los sub-DTO de catálogo)
│   ├── refresh.py                      # RefreshResult
│   └── report.py                       # ReportRequest (DashboardFilter + format + sections)
├── repositories/
│   ├── __init__.py
│   ├── dashboard_metric.py             # PLANO DE LECTURA: SUM sobre el rollup por rango+filtros, group_by segment
│   └── source_aggregation.py           # PLANO DE CÓMPUTO: agrega las FUENTES (queries del refresh, §3)
├── services/
│   ├── __init__.py
│   ├── metrics.py                      # compone FunnelSummary/TimeSeries/DistributionSummary/KpiSummary/DashboardMeta (lee el rollup + resuelve codes por catálogo)
│   ├── refresh.py                      # recomputa el rollup (ventana móvil) + upsert idempotente + set refresh_state
│   ├── report.py                       # genera PDF/Excel server-side leyendo el rollup (lazy import reportlab/openpyxl)
│   └── catalog.py                      # cachea code↔(name,color,flags,display_order) de lead_status/appointment_status (resolución por code, ADR-008)
└── routers/
    ├── __init__.py                     # aggregator: prefix="/dashboards"
    ├── metrics.py                      # POST funnel/leads-evolution/appointments-distribution/summary + GET meta (RBAC DASHBOARD_VIEW)
    ├── report.py                       # POST /report (RBAC REPORTS_EXPORT) → binario
    └── refresh.py                      # POST /internal/refresh (shared-secret, NO RBAC) — target Cloud Scheduler
```

> **No hay `models/associations.py`**: `dashboards` no introduce M:N (las 2 tablas son derivadas, sin relaciones ORM cross-módulo — todo lo de negocio se lee por `select()` directo sobre las tablas fuente).

> **No hay `bot_facade.py`**: el bot NO consume `dashboards` (el dashboard es de UI/reportes, no una tool). El único entrypoint de máquina es `/internal/refresh` (Cloud Scheduler), no el bot.

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean) — **en F1, NO en F0** (en F0 el paquete es INERTE):

```python
from app.modules import (  # noqa: F401
    admin, bots, calendar, catalog, clinic, conversations, crm, dashboards, marketing, scheduling, staff,
)
```

Y registrar el aggregator en `app/main.py` (un solo `include_router`, como el resto):

```python
from app.modules.dashboards.routers import router as dashboards_router

app.include_router(dashboards_router)  # prefix="/api/v1" + "/dashboards" interno
```

El aggregator `routers/__init__.py` replica el patrón de `scheduling`/`calendar`:

```python
"""
Agrega los sub-routers de dashboards bajo /dashboards. `main.py` incluye este `router`
una vez. ⚠ Orden de rutas: las ESTÁTICAS (/funnel, /summary, /meta, /report,
/internal/refresh) NO colisionan entre sí (todas literales). NO hay rutas paramétricas
/{id} (el módulo no tiene CRUD), así que el orden del aggregator es informativo.
"""

from fastapi import APIRouter

from app.modules.dashboards.routers.metrics import router as metrics_router
from app.modules.dashboards.routers.refresh import router as refresh_router
from app.modules.dashboards.routers.report import router as report_router

router = APIRouter(prefix="/dashboards")
router.include_router(metrics_router)   # /funnel, /leads-evolution, /appointments-distribution, /summary, /meta
router.include_router(report_router)    # /report
router.include_router(refresh_router)   # /internal/refresh

__all__ = ["router"]
```

## Enums — `enums.py` (en código, NO en BD)

`DashboardMetric` es un contrato **code-level estable** (NO un catálogo en BD — a diferencia de `lead_status`/`appointment_status`, que SÍ son catálogos configurables y se resuelven por `code`). Es el value de la columna `dashboard_daily_metric.metric` (varchar plano; Pydantic valida contra el enum, la BD almacena el slug).

```python
"""
Dashboards enums (code-level value sets, NO DB catalogs).
- DashboardMetric: el value de la columna `metric` del rollup. Cada miembro se materializa
  por día (× sede donde aplica, × segmento donde aplica) — ver §3 del README/backend.
  Los CODES de ESTADO (lead_status_code / appointment_status_code) que van en la columna
  `segment` NO se enuman aquí: son CATÁLOGOS configurables (ADR-008) → se resuelven por
  `code` desde lead_status/appointment_status (servicio `catalog`), nunca hardcodeados.
- ReportFormat: el formato del export (pdf | excel) — valida ReportRequest.format.
"""

from __future__ import annotations

from enum import StrEnum


class DashboardMetric(StrEnum):
    conversations = "conversations"            # COUNT(DISTINCT person_id) conversation; segment 'bot' | NULL
    leads_created = "leads_created"            # COUNT(DISTINCT person_id) lead_status_history from=NULL
    lead_stage = "lead_stage"                  # COUNT(DISTINCT person_id) por to_lead_status_id (segment=lead_status_code)
    appointments = "appointments"             # COUNT appointment por status_id (segment=appointment_status_code) + branch_id
    appointments_source = "appointments_source"  # COUNT appointment por source (segment=source)
    customers_new = "customers_new"            # COUNT(DISTINCT person_id) person_customer_status
    bot_turns = "bot_turns"                    # COUNT bot_event WHERE event_type='turn_completed'
    bot_cost = "bot_cost"                      # value=SUM(cost_estimated_usd); count=SUM(tokens_in+tokens_out)


class ReportFormat(StrEnum):
    pdf = "pdf"
    excel = "excel"
```

> ⚠ **`segment` NO es un enum**. Para `appointments` el `segment` es un `appointment_status.code` (`SCHEDULED`/`CONFIRMED`/…/`RESCHEDULED`); para `lead_stage` es un `lead_status.code` (`NUEVO`/`CONTACTADO`/…/`CITA_AGENDADA`); para `appointments_source` es un `AppointmentSource` value (`bot`/`advisor`/…); para `conversations` es `'bot'` o `NULL`. Esos codes vienen del **catálogo** (`crm.lead_status`, `scheduling.appointment_status`) o de enums de los módulos fuente — el refresh NO los inventa, los copia tal cual. La resolución a `{name, color, display_order}` la hace `services/catalog.py` (ADR-008: por `code`, nunca por id).

## Models — SQLAlchemy 2.0

**Mixins** (de `app.shared.base_model`): `PrimaryKeyMixin` (`id`), `ActiveMixin` (`active`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **Ambas tablas llevan PK·A·T y NO `SoftDeleteMixin`** — son **derivadas** (se truncan/upsertean por el job; no hay borrado lógico de un agregado). El `active` del `ActiveMixin` no tiene semántica de negocio aquí (queda `true`); se hereda por uniformidad con el resto del template.

> ⚠ **Sin SoftDelete a propósito**: el rollup es idempotente — el refresh reescribe el mismo valor para los días cerrados (inmutables) y recomputa el día en curso cada ciclo. No hay nada que "soft-deletear": un día/métrica/segmento que deja de existir simplemente no se vuelve a escribir (y el refresh borra+reinserta su ventana, ver §refresh). Esto **diverge** de los catálogos y entidades de negocio (que sí usan SD).

### `models/dashboard_daily_metric.py` — tabla `dashboard_daily_metric` — PK·A·T

Una fila por `(metric_date, branch_id, metric, segment)`. El plano de lectura **suma** sobre el rango de fechas y filtra por `branch_id`/`segment` — todo indexado, sub-segundo.

```python
"""
DashboardDailyMetric = la fact table del rollup diario (capa de agregación materializada).
Una fila por (metric_date, branch_id, metric, segment): el grano universal
(día × sede × métrica × segmento) → conteo/valor que cubre embudo, donut, línea y KPIs.
NO es una entidad de negocio: la repuebla el job de refresh agregando las fuentes
(crm/scheduling/conversations/bots). PK·A·T, SIN SoftDelete (derivada, upsert idempotente).

- branch_id NULLABLE = métrica a nivel CLÍNICA (conversaciones, leads, clientes, bot);
  con valor = métrica de CITAS por sede (solo `appointment` tiene branch_id — ver gotchas).
  FK LÓGICA a clinic.branch SIN constraint (ADR-009): el rollup se trunca/reescribe; un
  branch borrado no debe romper un INSERT del job.
- segment NULLABLE = desglose dentro de la métrica (status_code / lead_status_code / source /
  'bot'); NULL = métrica escalar.
- value Numeric(12,2) NULLABLE = monto/valor agregado (costo del bot, ingreso); NULL cuando
  la métrica es solo de conteo. Serializa como STRING en el wire.

UNIQUE (metric_date, branch_id, metric, segment) = el upsert idempotente del refresh.
⚠ branch_id/segment NULLABLE en un UNIQUE: en Postgres NULL != NULL → dos filas con
branch_id=NULL NO chocarían. El refresh por eso hace DELETE de la ventana + INSERT (no
ON CONFLICT sobre columnas nullables); ver services/refresh.py. El índice de cobertura
(metric, metric_date, branch_id) sirve el rango+filtro del plano de lectura.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class DashboardDailyMetric(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_daily_metric"
    __table_args__ = (
        UniqueConstraint(
            "metric_date", "branch_id", "metric", "segment",
            name="uq_dashboard_daily_metric_grain",
        ),
        Index(
            "ix_dashboard_daily_metric_lookup",
            "metric", "metric_date", "branch_id",
        ),
    )

    # Día del agregado (frontera UTC). El render local lo maneja el front.
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    # FK LÓGICA a clinic.branch (sin constraint, ADR-009). NULL = clínica entera.
    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # DashboardMetric value (code-level): conversations | leads_created | lead_stage | ...
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    # Desglose: status_code / lead_status_code / source / 'bot'. NULL = escalar.
    segment: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Conteo agregado.
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Valor monetario/numérico agregado (costo bot, ingreso). NULL = solo-conteo.
    value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
```

### `models/dashboard_refresh_state.py` — tabla `dashboard_refresh_state` — PK·A·T

Fila única (singleton) que guarda el estado del último job de refresh: alimenta el badge "Actualizado hace N min" del panel + el diagnóstico.

```python
"""
DashboardRefreshState = singleton de observabilidad del refresh. UNA fila (el service la
crea on-first-run y la actualiza in-place). NO es crítica para los datos del rollup; es
para la UX ("Actualizado hace N min" en el panel y en el `meta`) y el diagnóstico del job.
PK·A·T, SIN SoftDelete. status ∈ {ok, running, error}.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, TimestampMixin


class DashboardRefreshState(PrimaryKeyMixin, ActiveMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_refresh_state"

    # Último refresh OK (para "Actualizado hace N min"). NULL antes del primer run.
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Ventana (días) recomputada en el último ciclo.
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ok | running | error.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ok")
    # Último error del job (observabilidad; NO bloquea las lecturas).
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

### `models/__init__.py`

```python
"""
Importar los modelos acá los registra en Base.metadata antes de que Alembic lea el
esquema. Sin orden de dependencia entre ellos (no hay FK entre las 2 tablas).
"""

from app.modules.dashboards.models.dashboard_daily_metric import DashboardDailyMetric
from app.modules.dashboards.models.dashboard_refresh_state import DashboardRefreshState

__all__ = ["DashboardDailyMetric", "DashboardRefreshState"]
```

**Lazy strategy**: ninguna de las 2 tablas tiene `relationship(...)` (ni intra ni cross-módulo). El `branch_id` es una FK **lógica** (ADR-009, sin constraint) que se resuelve para la UI por id + un map de catálogo en `services/metrics.py` (`clinic.branch_repository.get_by_ids`, igual que `scheduling` resuelve `branch_name`). Cero N+1, cero join en el plano de lectura (el rollup es self-contained).

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (idénticas a [`../calendar/backend.md`](../calendar/backend.md#schemas-pydantic-v2--completos)): no usar Ellipsis (`...`) en `Field(...)`; `Annotated` solo para `Query`/`Path` en routers; validators con mensajes en inglés; `model_config = ConfigDict(from_attributes=True)` solo donde se serializa desde un modelo (estos schemas se arman a mano en los services, no `from_attributes`). **`value`/`bot_cost_usd` son `str`** en el wire (Numeric → string).

### `schemas/filter.py` — el request body común

```python
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator

_MAX_RANGE_DAYS = 366  # acota el SUM (rango ≤ 1 año + 1 por bisiesto)


class DashboardFilter(BaseModel):
    """Body común de las 4 lecturas POST + del report. branch_id None = clínica entera
    (etapas previas a 'cita' SIEMPRE son a nivel clínica — solo appointment tiene branch_id).
    source/campaign_id = filtros opcionales (source filtra appointments_source / segment 'bot';
    campaign_id reservado para atribución de campaña vía lead_status_history.source_campaign_id)."""

    date_from: date
    date_to: date
    branch_id: str | None = None
    source: str | None = None
    campaign_id: str | None = None

    @model_validator(mode="after")
    def _validate_range(self) -> "DashboardFilter":
        if self.date_to < self.date_from:
            # El service lo re-mapea a DASHBOARD_INVALID_DATE_RANGE (400). El validator
            # Pydantic da el 422 de forma; el service da el 400 de dominio con `code`.
            raise ValueError("date_to must be >= date_from")
        if (self.date_to - self.date_from).days > _MAX_RANGE_DAYS:
            raise ValueError(f"date range must be <= {_MAX_RANGE_DAYS} days")
        return self
```

> ⚠ **Doble validación de rango** (Pydantic + service): el `model_validator` aquí da el feedback temprano (422), pero el **contrato de error de la spec §8 es `DASHBOARD_INVALID_DATE_RANGE` (400)**. Para que el cliente reciba el `code` de dominio, `services/metrics.py` **re-valida** el rango al entrar (lanza `BadRequestException(code="DASHBOARD_INVALID_DATE_RANGE")`) — la precedencia del CONTRATO gana (lección §22). En la práctica el front re-valida con Zod y nunca llega un rango inválido; el guard del service es el backstop autoritativo. (Alternativa: quitar el `model_validator` y validar SOLO en el service para no duplicar; **decidir en F1** — el doc deja ambos para no depender del orden de evaluación.)

### `schemas/funnel.py`

```python
from __future__ import annotations

from pydantic import BaseModel


class FunnelStage(BaseModel):
    """Una etapa del embudo (6). rate_from_prev = count_etapa / count_etapa_anterior
    (None en la 1ª etapa). color = del catálogo o token Fluent (resuelto en el service)."""

    key: str           # 'conversations' | 'leads' | 'engaged' | 'appointments' | 'confirmed' | 'customers'
    label: str         # etiqueta ES ('Conversaciones', 'Leads', ...)
    count: int
    rate_from_prev: float | None = None
    color: str | None = None


class FunnelSummary(BaseModel):
    """Respuesta de POST /funnel. 6 etapas + las tasas agregadas (KPIs del embudo)."""

    stages: list[FunnelStage]
    conversion_rate: float       # lead_stage[CITA_AGENDADA] / leads_created (KPI HU26)
    total_leads: int
    total_appointments: int
    total_customers: int
    chatbot_share: float         # conversations[bot] / conversations (aporte del chatbot)
```

### `schemas/series.py`

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class TimeSeriesPoint(BaseModel):
    """Un punto de la línea de evolución. `date` = ISO date (str). `values` = una clave por
    serie (p.ej. por lead_status_code) → conteo de ese día. Las claves ausentes = 0 en el front."""

    date: str                                # 'YYYY-MM-DD'
    values: dict[str, int] = Field(default_factory=dict)


class _SeriesMeta(BaseModel):
    """Definición de una serie (para la leyenda + el color del chart)."""

    key: str          # lead_status_code
    label: str        # nombre del catálogo (ES)
    color: str | None = None  # lead_status.color


class TimeSeries(BaseModel):
    """Respuesta de POST /leads-evolution. series = las definiciones (leyenda/color);
    points = un punto por día del rango (bucketizado, días sin datos incluidos con 0)."""

    series: list[_SeriesMeta]
    points: list[TimeSeriesPoint]
```

### `schemas/distribution.py`

```python
from __future__ import annotations

from pydantic import BaseModel


class DistributionBucket(BaseModel):
    """Una porción del donut. code = appointment_status_code; label/color del catálogo."""

    code: str
    label: str
    color: str | None = None
    count: int


class DistributionSummary(BaseModel):
    """Respuesta de POST /appointments-distribution. buckets = citas por estado (donut);
    total = suma (centro del donut). Excluye RESCHEDULED del 'total agendadas' del embudo,
    pero el donut SÍ puede mostrar la porción RESCHEDULED como estado-actual (no doble-cuenta
    porque cuenta filas por status_id, no transiciones — ver gotchas)."""

    buckets: list[DistributionBucket]
    total: int
```

### `schemas/summary.py`

```python
from __future__ import annotations

from pydantic import BaseModel


class KpiSummary(BaseModel):
    """Respuesta de POST /summary. Tasas (float, 0..1 — el front formatea a %) + escalares
    (int) + el costo del bot (str: Numeric serializa como string)."""

    # Tasas derivadas (numerador/denominador en §7 del README; 0.0 si el denominador es 0).
    conversion_rate: float        # lead_stage[CITA_AGENDADA] / leads_created
    lead_to_appt_rate: float      # appointments(agendadas) / leads_created
    confirmation_rate: float      # appointments[CONFIRMED+downstream] / appointments(total)
    show_rate: float              # appointments[ATTENDED] / (ATTENDED + NO_SHOW)
    no_show_rate: float           # appointments[NO_SHOW] / (ATTENDED + NO_SHOW)
    customer_rate: float          # customers_new / appointments[ATTENDED] (o / leads_created)
    # Escalares.
    total_conversations: int
    conversations_bot: int
    total_leads: int
    total_appointments: int
    total_confirmed: int
    total_attended: int
    total_customers: int
    bot_turns: int
    # Numeric → STRING en el wire (regla del template).
    bot_cost_usd: str
```

### `schemas/meta.py`

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class _StatusOption(BaseModel):
    """Un estado del catálogo (lead o appointment) para los colores del chart + leyenda."""

    code: str
    name: str
    color: str | None = None
    display_order: int


class _BranchOption(BaseModel):
    """Una sede para el select de filtro."""

    id: str
    name: str


class DashboardMeta(BaseModel):
    """Respuesta de GET /meta. Alimenta los selects (sedes/orígenes) + los colores/labels de
    los charts (estados) + el badge 'Actualizado hace N min' (last_refreshed_at)."""

    last_refreshed_at: str | None = None   # ISO 8601 UTC; None antes del primer refresh
    lead_statuses: list[_StatusOption] = Field(default_factory=list)
    appointment_statuses: list[_StatusOption] = Field(default_factory=list)
    branches: list[_BranchOption] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)  # AppointmentSource values presentes
```

### `schemas/refresh.py`

```python
from __future__ import annotations

from pydantic import BaseModel


class RefreshResult(BaseModel):
    """Respuesta de POST /internal/refresh (target Cloud Scheduler). Observabilidad del job."""

    refreshed_at: str       # ISO 8601 UTC del refresh recién hecho
    window_days: int
    rows_written: int       # filas del rollup upserteadas
    status: str             # 'ok' | 'error'
```

### `schemas/report.py`

```python
from __future__ import annotations

from pydantic import Field

from app.modules.dashboards.enums import ReportFormat
from app.modules.dashboards.schemas.filter import DashboardFilter


class ReportRequest(DashboardFilter):
    """Body de POST /report = DashboardFilter (rango+sede) + el formato + las secciones a
    incluir. format inválido → REPORT_FORMAT_NOT_SUPPORTED (400). sections vacío = todas."""

    format: ReportFormat
    sections: list[str] = Field(default_factory=list)  # 'kpis' | 'funnel' | 'distribution' | 'evolution'
```

> ⚠ `ReportRequest` **hereda** de `DashboardFilter` → reusa la validación de rango. `format` es un `ReportFormat` (Pydantic rechaza otro value con 422; el service re-mapea a `REPORT_FORMAT_NOT_SUPPORTED` 400 si llega como string libre por compatibilidad — ver `report.py`).

## Repositories

`dashboards` tiene **dos repositorios de naturaleza opuesta**: uno lee el **plano caliente** (el rollup; barato, por request) y otro agrega el **plano frío** (las fuentes; caro, solo el job). Ninguno expone `/list` paginado.

> `ALLOWED_FIELDS` = `set()` en ambos: **no hay listado dinámico** del rollup desde el front (no se expone `POST /list`). Las lecturas son agregaciones fijas con `DashboardFilter`, no `QueryRequest`. (Igual que `marketing.promotion_usage` no expone el rollup como tabla filtrable salvo lo estrictamente real.)

### `repositories/dashboard_metric.py` — PLANO DE LECTURA (SUM sobre el rollup)

Molde exacto `marketing/repositories/promotion_usage.py:64-77` (`func.count` / `func.coalesce(func.sum(...), 0)` / `group_by`). Suma el rollup por rango+filtros; el `group_by(segment)` arma el desglose (donut/línea/embudo); el `value` nullable se `COALESCE`a.

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dashboards.models.dashboard_daily_metric import DashboardDailyMetric
from app.shared.base_repository import BaseRepository


class DashboardMetricRepository(BaseRepository[DashboardDailyMetric]):
    ALLOWED_FIELDS: set[str] = set()  # sin /list dinámico; las lecturas son agregaciones fijas

    def __init__(self) -> None:
        super().__init__(DashboardDailyMetric)

    def _range(self, q, *, metric: str, date_from: date, date_to: date, branch_id: str | None):
        """Filtro base compartido: una métrica, el rango [date_from, date_to], y la sede.
        branch_id None = NO filtra por sede (suma clínica entera, incl. filas branch_id NULL).
        branch_id con valor = SOLO esa sede (las filas branch_id NULL — métricas de clínica —
        quedan fuera; por eso el funnel mezcla escalas con cuidado, ver metrics.py)."""
        q = q.where(
            DashboardDailyMetric.metric == metric,
            DashboardDailyMetric.metric_date >= date_from,
            DashboardDailyMetric.metric_date <= date_to,
        )
        if branch_id is not None:
            q = q.where(DashboardDailyMetric.branch_id == branch_id)
        return q

    async def sum_scalar(
        self, db: AsyncSession, *, metric: str, date_from: date, date_to: date,
        branch_id: str | None = None, segment: str | None = None,
    ) -> Row[tuple[int, Decimal]]:
        """Row(sum_count, sum_value) de UNA métrica (opcionalmente UN segmento) en el rango.
        coalesce evita NULL cuando no hay filas (rollup vacío → 0, NO error — spec §8)."""
        q = self._range(
            select(
                func.coalesce(func.sum(DashboardDailyMetric.count), 0),
                func.coalesce(func.sum(DashboardDailyMetric.value), 0),
            ),
            metric=metric, date_from=date_from, date_to=date_to, branch_id=branch_id,
        )
        if segment is not None:
            q = q.where(DashboardDailyMetric.segment == segment)
        return (await db.execute(q)).one()

    async def sum_by_segment(
        self, db: AsyncSession, *, metric: str, date_from: date, date_to: date,
        branch_id: str | None = None,
    ) -> dict[str, int]:
        """{segment: sum_count} — el desglose del DONUT (appointments por status_code) y del
        EMBUDO de lead (lead_stage por lead_status_code). group_by(segment). Las filas con
        segment NULL (escalares) se agrupan bajo la clave '' (el caller las ignora o las usa
        como total)."""
        q = self._range(
            select(DashboardDailyMetric.segment, func.coalesce(func.sum(DashboardDailyMetric.count), 0)),
            metric=metric, date_from=date_from, date_to=date_to, branch_id=branch_id,
        ).group_by(DashboardDailyMetric.segment)
        return {(row[0] or ""): row[1] for row in (await db.execute(q)).all()}

    async def sum_by_date_segment(
        self, db: AsyncSession, *, metric: str, date_from: date, date_to: date,
        branch_id: str | None = None,
    ) -> dict[tuple[date, str], int]:
        """{(metric_date, segment): sum_count} — la LÍNEA de evolución (lead_stage por día ×
        lead_status_code). group_by(metric_date, segment). El service bucketiza a TimeSeriesPoint
        rellenando los días faltantes con 0."""
        q = self._range(
            select(
                DashboardDailyMetric.metric_date,
                DashboardDailyMetric.segment,
                func.coalesce(func.sum(DashboardDailyMetric.count), 0),
            ),
            metric=metric, date_from=date_from, date_to=date_to, branch_id=branch_id,
        ).group_by(DashboardDailyMetric.metric_date, DashboardDailyMetric.segment)
        return {(row[0], row[1] or ""): row[2] for row in (await db.execute(q)).all()}

    async def delete_window(
        self, db: AsyncSession, *, date_from: date, date_to: date
    ) -> None:
        """Refresh paso 0: borra la ventana móvil ANTES de reinsertar (idempotencia sin
        ON CONFLICT sobre columnas nullables — branch_id/segment NULL no chocan en un UNIQUE).
        DELETE real (la tabla es derivada, sin SoftDelete)."""
        from sqlalchemy import delete
        await db.execute(
            delete(DashboardDailyMetric).where(
                DashboardDailyMetric.metric_date >= date_from,
                DashboardDailyMetric.metric_date <= date_to,
            )
        )


dashboard_metric_repository = DashboardMetricRepository()
```

> ⚠ **Por qué DELETE+INSERT y no `ON CONFLICT`/upsert**: el UNIQUE `(metric_date, branch_id, metric, segment)` tiene **2 columnas NULLABLE** (`branch_id`, `segment`). En Postgres `NULL` nunca colisiona con `NULL` en un UNIQUE → un `ON CONFLICT (metric_date, branch_id, metric, segment) DO UPDATE` **no dispara** para las métricas a nivel clínica (`branch_id=NULL`) ni para las escalares (`segment=NULL`) → duplicaría filas en cada ciclo. La idempotencia se logra con **`DELETE` de la ventana móvil + `INSERT` del recómputo**, en la misma tx del refresh. (Es la estrategia estándar de un rollup re-materializable.)

### `repositories/source_aggregation.py` — PLANO DE CÓMPUTO (agrega las FUENTES, §3)

El **único** punto que escanea las tablas de negocio. Una query por `DashboardMetric`, con las **fórmulas EXACTAS** de la spec §3. Todas filtran `deleted_at IS NULL` donde la fuente tiene `SoftDeleteMixin` (`conversation`, `appointment`, `person_customer_status`) y NO donde es append-only (`lead_status_history`, `bot_event` — sin SD). El bucketing por día usa **`date_trunc`/`cast(... AS Date)`** (Postgres) → en el smoke sqlite se bucketiza en Python (ver gotcha `date_trunc`).

```python
"""
Plano de CÓMPUTO del refresh: agrega las TABLAS FUENTE (read-only) → tuplas
(metric_date, branch_id, segment, count, value) que el service inserta en el rollup.
Fuentes y columnas temporales EXACTAS (mapeadas del código real 2026-06-24):
- conversation.opened_at          (conversations/models/conversation.py:68)
- lead_status_history.changed_at  (crm/models/lead_status_history.py:34; from_lead_status_id:26, to_lead_status_id:29)
- appointment.scheduled_for       (scheduling/models/appointment.py:57; status_id:60, source:64, branch_id:54)
- person_customer_status.became_customer_at (crm/models/person_customer_status.py:52)
- bot_event.created_on            (TimestampMixin; event_type:47, tokens_in/out:51-52, cost_estimated_usd:54)

⚠ date_trunc / cast a Date es Postgres-only → en sqlite (smoke) el service bucketiza en
Python (lee filas crudas con su timestamp y agrupa por .date()). El gating Postgres-vs-sqlite
vive en el SERVICE (refresh.py), no acá: estas funciones tienen variante `*_pg` (SQL group_by)
y el service elige; el doc muestra la variante Postgres (la de prod).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.models.bot_event import BotEvent
from app.modules.conversations.models.conversation import Conversation
from app.modules.crm.models.lead_status_history import LeadStatusHistory
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.scheduling.models.appointment import Appointment
from app.modules.scheduling.models.appointment_status import AppointmentStatus


class SourceAggregationRepository:
    """NO extiende BaseRepository: no es una entidad propia, es un agregador de fuentes."""

    # ── conversations: COUNT(DISTINCT person_id) por opened_at::date; segment 'bot' | NULL ──
    async def conversations_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """Escalar (segment NULL), branch_id NULL (conversation no tiene branch_id). DISTINCT
        person_id (no cuenta hilos duplicados de la misma persona)."""
        day = cast(Conversation.opened_at, type_=None)  # ← date_trunc/cast en _pg helper real
        q = (
            select(func.date(Conversation.opened_at), func.count(func.distinct(Conversation.person_id)))
            .where(
                Conversation.opened_at >= since,
                Conversation.opened_at < until,
                Conversation.deleted_at.is_(None),
                Conversation.person_id.is_not(None),
            )
            .group_by(func.date(Conversation.opened_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    async def conversations_bot_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """segment='bot': assignee_type='bot' OR EXISTS(bot_event de esa conversación)."""
        bot_conv = select(BotEvent.conversation_id).where(
            BotEvent.conversation_id == Conversation.id
        ).exists()
        q = (
            select(func.date(Conversation.opened_at), func.count(func.distinct(Conversation.person_id)))
            .where(
                Conversation.opened_at >= since,
                Conversation.opened_at < until,
                Conversation.deleted_at.is_(None),
                Conversation.person_id.is_not(None),
                (Conversation.assignee_type == "bot") | bot_conv,
            )
            .group_by(func.date(Conversation.opened_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── leads_created: COUNT(DISTINCT person_id) WHERE from_lead_status_id IS NULL ──
    async def leads_created_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """from_lead_status_id IS NULL = la fila de NACIMIENTO del lead (cada lead nace en NUEVO).
        Por changed_at::date. lead_status_history NO tiene SoftDelete (append-only) → sin filtro
        deleted_at. branch_id NULL (lead no tiene sede)."""
        q = (
            select(func.date(LeadStatusHistory.changed_at), func.count(func.distinct(LeadStatusHistory.person_id)))
            .where(
                LeadStatusHistory.changed_at >= since,
                LeadStatusHistory.changed_at < until,
                LeadStatusHistory.from_lead_status_id.is_(None),
            )
            .group_by(func.date(LeadStatusHistory.changed_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── lead_stage: COUNT(DISTINCT person_id) por to_lead_status_id (segment=lead_status_code) + día ──
    async def lead_stage_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, str, int]]:
        """(día, lead_status_code, count). JOIN a lead_status para devolver el CODE (no el id —
        ADR-008: el rollup persiste el code, estable, NO el uuid). Alimenta la línea + las etapas
        3/conversión del embudo. DISTINCT person_id por (día, estado destino)."""
        q = (
            select(
                func.date(LeadStatusHistory.changed_at),
                LeadStatus.code,
                func.count(func.distinct(LeadStatusHistory.person_id)),
            )
            .join(LeadStatus, LeadStatus.id == LeadStatusHistory.to_lead_status_id)
            .where(
                LeadStatusHistory.changed_at >= since,
                LeadStatusHistory.changed_at < until,
            )
            .group_by(func.date(LeadStatusHistory.changed_at), LeadStatus.code)
        )
        return [(row[0], row[1], row[2]) for row in (await db.execute(q)).all()]

    # ── appointments: COUNT por status_code (segment) + scheduled_for::date + branch_id ──
    async def appointments_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, str | None, str, int]]:
        """(día, branch_id, appointment_status_code, count). JOIN a appointment_status → CODE.
        Alimenta el donut + las etapas 4/5. branch_id es REAL (denorm). Excluir RESCHEDULED del
        agregado 'agendadas' se hace en el SERVICE (no acá: el donut SÍ quiere la porción
        RESCHEDULED como estado-actual). deleted_at IS NULL (appointment soft-deletea solo
        errores de captura)."""
        q = (
            select(
                func.date(Appointment.scheduled_for),
                Appointment.branch_id,
                AppointmentStatus.code,
                func.count(),
            )
            .join(AppointmentStatus, AppointmentStatus.id == Appointment.status_id)
            .where(
                Appointment.scheduled_for >= since,
                Appointment.scheduled_for < until,
                Appointment.deleted_at.is_(None),
            )
            .group_by(func.date(Appointment.scheduled_for), Appointment.branch_id, AppointmentStatus.code)
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await db.execute(q)).all()]

    # ── appointments_source: COUNT por source (segment) + día + branch_id ──
    async def appointments_source_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, str | None, str, int]]:
        """(día, branch_id, source, count). source = AppointmentSource value ('bot'/'advisor'/…).
        Atribución al chatbot (etapa 4 sub-conteo + chatbot_share)."""
        q = (
            select(
                func.date(Appointment.scheduled_for),
                Appointment.branch_id,
                Appointment.source,
                func.count(),
            )
            .where(
                Appointment.scheduled_for >= since,
                Appointment.scheduled_for < until,
                Appointment.deleted_at.is_(None),
            )
            .group_by(func.date(Appointment.scheduled_for), Appointment.branch_id, Appointment.source)
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await db.execute(q)).all()]

    # ── customers_new: COUNT(DISTINCT person_id) por became_customer_at::date ──
    async def customers_new_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """became_customer_at = lo fija solo attend()→ATTENDED (atómico). deleted_at IS NULL
        (la fila se soft-deletea al cerrar el hilo cliente, pero became_customer_at del rango
        sigue siendo el evento de conversión). branch_id NULL (cliente no tiene sede directa)."""
        q = (
            select(func.date(PersonCustomerStatus.became_customer_at), func.count(func.distinct(PersonCustomerStatus.person_id)))
            .where(
                PersonCustomerStatus.became_customer_at >= since,
                PersonCustomerStatus.became_customer_at < until,
                PersonCustomerStatus.deleted_at.is_(None),
            )
            .group_by(func.date(PersonCustomerStatus.became_customer_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── bot_turns: COUNT WHERE event_type='turn_completed' por created_on::date ──
    async def bot_turns_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """SOLO event_type='turn_completed' (un turno emite varios eventos — NO COUNT(*) de toda
        la tabla). bot_event NO tiene SoftDelete (append-only)."""
        q = (
            select(func.date(BotEvent.created_on), func.count())
            .where(
                BotEvent.created_on >= since,
                BotEvent.created_on < until,
                BotEvent.event_type == "turn_completed",
            )
            .group_by(func.date(BotEvent.created_on))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── bot_cost: value=SUM(COALESCE(cost,0)); count=SUM(COALESCE(tokens_in,0)+COALESCE(tokens_out,0)) ──
    async def bot_cost_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int, "Decimal"]]:
        """(día, total_tokens, total_cost_usd). COALESCE en TODO (tokens/cost nullables → §13).
        cast a Numeric para no perder precisión. Sin filtro de event_type (todos los eventos
        aportan tokens/costo si los tienen)."""
        q = (
            select(
                func.date(BotEvent.created_on),
                func.coalesce(func.sum(func.coalesce(BotEvent.tokens_in, 0) + func.coalesce(BotEvent.tokens_out, 0)), 0),
                func.coalesce(func.sum(func.coalesce(cast(BotEvent.cost_estimated_usd, Numeric(12, 2)), 0)), 0),
            )
            .where(
                BotEvent.created_on >= since,
                BotEvent.created_on < until,
            )
            .group_by(func.date(BotEvent.created_on))
        )
        return [(row[0], row[1], row[2]) for row in (await db.execute(q)).all()]


source_aggregation_repository = SourceAggregationRepository()
```

> ⚠ **`func.date(...)` vs `date_trunc`**: para el grano DÍA, `func.date(col)` compila a `CAST(col AS DATE)` en Postgres y a `date(col)` en sqlite — **funciona en ambos** (es lo que se muestra). Si en algún punto se necesitara un grano mayor (`date_trunc('week', ...)`), eso es **Postgres-only** y obliga a bucketizar en Python en el smoke (gotcha §13). El doc usa `func.date` precisamente para que el `group_by` por día **sí** corra idéntico en el smoke. Verificar en F1 que `func.date` sobre un `timestamptz` respeta la frontera UTC (las fuentes guardan UTC; el cast a date corta en medianoche UTC = `metric_date`).

> ⚠ **`leads_created` no se JOIN-ea a `lead_status`** (no necesita el code: la condición es `from_lead_status_id IS NULL`). **`lead_stage` y `appointments` SÍ JOIN-ean** a su catálogo para persistir el `code` (no el uuid) en `segment` — así el rollup es estable aunque admin renombre/reordene un estado (ADR-008). Importar el MODEL de otro módulo para un read es **cycle-safe** (lección §22: el importado solo alcanza models leaf).

## Services

### `services/catalog.py` — resolución por code (ADR-008, NO hardcode)

El servicio que materializa la regla "resolver estados por `code`/flags, nunca por id". Lee `crm.lead_status` y `scheduling.appointment_status` y arma maps `code → (name, color, display_order, flags)`. Lo usan `metrics` (labels/colores del chart + qué codes son etapa 3/won/confirmado) y `report`.

```python
"""
Resolución de catálogos de estado por CODE (ADR-008). NO hardcodea ids ni asume el orden:
lee lead_status / appointment_status (catálogos en BD, configurables por admin) y expone
los codes + sus flags (is_won/is_final/is_active_attention) para que metrics.py componga el
embudo y los KPIs SIN ids mágicos. Cachear por request (no por proceso: admin puede editar
el catálogo sin redeploy → un cache de proceso quedaría stale; el costo es 2 SELECT chicos).
"""

from __future__ import annotations

from app.modules.crm.repositories.lead_status import lead_status_repository
from app.modules.scheduling.repositories.appointment_status import appointment_status_repository

# Codes de la etapa 3 del embudo (Contactados/Interesados). Resueltos por CODE, no por id.
# Si el catálogo cambia los codes, ESTA lista es el único punto a tocar (o derivar por flags).
ENGAGED_LEAD_CODES = {"CONTACTADO", "INTERESADO", "EVALUANDO"}


async def lead_status_map(db) -> dict[str, dict]:
    """{code: {name, color, display_order, is_won, is_final}}. El code 'won' (CITA_AGENDADA)
    se descubre por flag is_won, NO por string — robusto a renombrados (ADR-008)."""
    statuses = await lead_status_repository.list_all(db)  # vivos, ordenados por display_order
    return {
        s.code: {
            "name": s.name, "color": s.color, "display_order": s.display_order,
            "is_won": s.is_won, "is_final": s.is_final,
        }
        for s in statuses
    }


async def appointment_status_map(db) -> dict[str, dict]:
    """{code: {name, color, display_order, is_final, is_active_attention}}. CONFIRMED/ATTENDED/
    NO_SHOW/RESCHEDULED se resuelven por code (estables, MAYÚSCULAS, inmutables — seed.py:404)."""
    statuses = await appointment_status_repository.list_all(db)
    return {
        s.code: {
            "name": s.name, "color": s.color, "display_order": s.display_order,
            "is_final": s.is_final, "is_active_attention": s.is_active_attention,
        }
        for s in statuses
    }


def won_lead_code(lead_map: dict[str, dict]) -> str | None:
    """El code is_won (CITA_AGENDADA en el seed) descubierto por FLAG, no hardcodeado."""
    for code, meta in lead_map.items():
        if meta["is_won"]:
            return code
    return None
```

> ⚠ **Resolver por flag, no por string** donde se puede: el numerador de la tasa de conversión es `lead_stage[code_won] / leads_created`, y `code_won` se descubre con `is_won=true` (función `won_lead_code`), no con el literal `"CITA_AGENDADA"`. La etapa 3 (`ENGAGED_LEAD_CODES`) es la única que enumera codes (no hay un flag "engaged" en el catálogo) — es el punto único a ajustar si la clínica reconfigura el embudo. Esto cumple ADR-008 (la spec §13: NO id hardcodeado).

### `services/metrics.py` — compone las 4 lecturas + meta (lee el rollup)

```python
"""
Plano de LECTURA del panel. Cada función arma su response SUMANDO el rollup
(dashboard_metric_repository) sobre el rango+filtros del DashboardFilter + resolviendo los
codes a labels/colores con catalog.py (ADR-008). NUNCA escanea las fuentes (eso es refresh).
Rollup vacío → conteos 0 (NO error, spec §8). Lanza BadRequestException(DASHBOARD_INVALID_DATE_RANGE)
si el rango es inválido (contrato §8; backstop de la validación Pydantic).
"""

from __future__ import annotations

from app.core.exceptions import BadRequestException
from app.modules.clinic.repositories.branch import branch_repository
from app.modules.dashboards.enums import DashboardMetric
from app.modules.dashboards.repositories.dashboard_metric import dashboard_metric_repository
from app.modules.dashboards.repositories.dashboard_refresh_state import refresh_state_repository
from app.modules.dashboards.schemas.filter import DashboardFilter
from app.modules.dashboards.schemas.funnel import FunnelStage, FunnelSummary
from app.modules.dashboards.services import catalog
from app.shared.base_schemas import SingleResponse

_MAX_RANGE_DAYS = 366


def _guard_range(f: DashboardFilter) -> None:
    """Backstop del contrato §8: el code de dominio gana sobre el 422 de Pydantic."""
    if f.date_to < f.date_from or (f.date_to - f.date_from).days > _MAX_RANGE_DAYS:
        raise BadRequestException(
            "Rango de fechas inválido (date_to < date_from o más de 366 días)",
            code="DASHBOARD_INVALID_DATE_RANGE",
        )


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


async def get_funnel(db, f: DashboardFilter) -> SingleResponse[FunnelSummary]:
    _guard_range(f)
    lead_map = await catalog.lead_status_map(db)
    won = catalog.won_lead_code(lead_map)  # CITA_AGENDADA por flag is_won

    # Etapas 1-3 + 6 = clínica entera (branch_id NULL ignora la sede); 4-5 = por sede si se filtró.
    conv = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.conversations, date_from=f.date_from, date_to=f.date_to)
    conv_bot = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.conversations, date_from=f.date_from, date_to=f.date_to, segment="bot")
    leads = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.leads_created, date_from=f.date_from, date_to=f.date_to)
    lead_by_stage = await dashboard_metric_repository.sum_by_segment(
        db, metric=DashboardMetric.lead_stage, date_from=f.date_from, date_to=f.date_to)
    appt_by_status = await dashboard_metric_repository.sum_by_segment(
        db, metric=DashboardMetric.appointments, date_from=f.date_from, date_to=f.date_to, branch_id=f.branch_id)

    engaged = sum(lead_by_stage.get(c, 0) for c in catalog.ENGAGED_LEAD_CODES)
    appt_total = sum(v for code, v in appt_by_status.items() if code != "RESCHEDULED")  # excluir hija
    confirmed = sum(appt_by_status.get(c, 0) for c in ("CONFIRMED", "ATTENDED"))
    customers = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.customers_new, date_from=f.date_from, date_to=f.date_to)

    stages = [
        FunnelStage(key="conversations", label="Conversaciones", count=conv.t[0], rate_from_prev=None),
        FunnelStage(key="leads", label="Leads", count=leads.t[0], rate_from_prev=_rate(leads.t[0], conv.t[0])),
        FunnelStage(key="engaged", label="Contactados/Interesados", count=engaged, rate_from_prev=_rate(engaged, leads.t[0])),
        FunnelStage(key="appointments", label="Citas agendadas", count=appt_total, rate_from_prev=_rate(appt_total, engaged)),
        FunnelStage(key="confirmed", label="Citas confirmadas", count=confirmed, rate_from_prev=_rate(confirmed, appt_total)),
        FunnelStage(key="customers", label="Clientes", count=customers.t[0], rate_from_prev=_rate(customers.t[0], confirmed)),
    ]
    return SingleResponse(data=FunnelSummary(
        stages=stages,
        conversion_rate=_rate(lead_by_stage.get(won or "", 0), leads.t[0]),
        total_leads=leads.t[0], total_appointments=appt_total, total_customers=customers.t[0],
        chatbot_share=_rate(conv_bot.t[0], conv.t[0]),
    ))


# get_leads_evolution(db, f) -> SingleResponse[TimeSeries]:
#   sum_by_date_segment(lead_stage) → bucketiza a TimeSeriesPoint (1 punto por día del rango,
#   días sin datos con {}); series = los lead_status_code presentes con su name/color del catálogo.
# get_appointments_distribution(db, f) -> SingleResponse[DistributionSummary]:
#   sum_by_segment(appointments, branch_id) → un bucket por appointment_status_code con
#   label/color del catálogo; total = suma (el donut SÍ muestra RESCHEDULED como estado-actual).
# get_summary(db, f) -> SingleResponse[KpiSummary]:
#   sum_scalar de cada métrica + las tasas (_rate); bot_cost_usd = str(sum_value de bot_cost).
# get_meta(db) -> SingleResponse[DashboardMeta]:
#   refresh_state.last_refreshed_at + lead_status_map/appointment_status_map (codes+colores) +
#   branch_repository.list_all (sedes para el select) + los AppointmentSource presentes.
```

> ⚠ **`.t[0]`** es taquigrafía del doc para "el `sum_count` del `Row`" (en el código real se desempaqueta el `Row` por índice: `row = await ...; count = row[0]`). El detalle que importa: **`appt_total` excluye `RESCHEDULED`** (la cita hija del reagendamiento → no doble-cuenta, gotcha §13); el donut (`get_appointments_distribution`) **NO** la excluye (muestra el estado-actual). **`conversion_rate`** usa el code descubierto por `is_won` (no el literal). Una división por 0 (rollup vacío) → `0.0`, nunca un error (spec §8). El **filtro por sede** (`branch_id`) solo se pasa a `appointments`/`appointments_source` (las únicas con `branch_id`); las etapas previas suman clínica entera SIEMPRE (gotcha: solo `appointment` tiene `branch_id`).

### `services/refresh.py` — recomputa el rollup (ventana móvil) + upsert idempotente

```python
"""
Plano de CÓMPUTO (frío, por cron). Recalcula el rollup sobre la VENTANA MÓVIL
[hoy - WINDOW_DAYS, hoy] + el día en curso, agregando las fuentes (source_aggregation_repository)
y reescribiendo dashboard_daily_metric (DELETE de la ventana + INSERT — idempotente, sin
ON CONFLICT sobre columnas nullables). Setea dashboard_refresh_state (status/last_refreshed_at).
Es el ÚNICO punto que escanea las fuentes. Lo dispara Cloud Scheduler vía /internal/refresh.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.core.config import get_settings
from app.modules.dashboards.enums import DashboardMetric
from app.modules.dashboards.models.dashboard_daily_metric import DashboardDailyMetric
from app.modules.dashboards.repositories.dashboard_metric import dashboard_metric_repository
from app.modules.dashboards.repositories.dashboard_refresh_state import refresh_state_repository
from app.modules.dashboards.repositories.source_aggregation import source_aggregation_repository
from app.modules.dashboards.schemas.refresh import RefreshResult
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now

_SYSTEM = "SYSTEM"  # actor del job (no hay user real)


async def run_refresh(db) -> SingleResponse[RefreshResult]:
    settings = get_settings()
    window = settings.DASHBOARD_REFRESH_WINDOW_DAYS
    now = utc_now()
    date_to = now.date()
    date_from = date_to - timedelta(days=window)
    since = datetime(date_from.year, date_from.month, date_from.day, tzinfo=now.tzinfo)
    until = now  # hasta el instante actual (incluye el día en curso)

    state = await refresh_state_repository.get_singleton(db)  # crea on-first-run
    state.status = "running"; state.window_days = window
    await db.flush()

    try:
        # 0) borra la ventana móvil (idempotencia).
        await dashboard_metric_repository.delete_window(db, date_from=date_from, date_to=date_to)
        rows: list[DashboardDailyMetric] = []

        # 1) agrega cada métrica de las fuentes → filas del rollup.
        for d, c in await source_aggregation_repository.conversations_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.conversations, None, c))
        for d, c in await source_aggregation_repository.conversations_bot_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.conversations, "bot", c))
        for d, c in await source_aggregation_repository.leads_created_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.leads_created, None, c))
        for d, code, c in await source_aggregation_repository.lead_stage_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.lead_stage, code, c))
        for d, branch, code, c in await source_aggregation_repository.appointments_by_day(db, since=since, until=until):
            rows.append(_row(d, branch, DashboardMetric.appointments, code, c))
        for d, branch, src, c in await source_aggregation_repository.appointments_source_by_day(db, since=since, until=until):
            rows.append(_row(d, branch, DashboardMetric.appointments_source, src, c))
        for d, c in await source_aggregation_repository.customers_new_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.customers_new, None, c))
        for d, c in await source_aggregation_repository.bot_turns_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.bot_turns, None, c))
        for d, tokens, cost in await source_aggregation_repository.bot_cost_by_day(db, since=since, until=until):
            rows.append(_row(d, None, DashboardMetric.bot_cost, None, tokens, value=cost))

        db.add_all(rows)
        await db.flush()
        state.status = "ok"; state.last_refreshed_at = now; state.last_error = None
        await db.flush()
        return SingleResponse(data=RefreshResult(
            refreshed_at=now.isoformat(), window_days=window, rows_written=len(rows), status="ok"))
    except Exception as exc:  # noqa: BLE001 — el job marca error y devuelve 'error' (NO 5xx silencioso)
        state.status = "error"; state.last_error = str(exc)[:500]
        await db.flush()
        return SingleResponse(data=RefreshResult(
            refreshed_at=now.isoformat(), window_days=window, rows_written=0, status="error"))


def _row(metric_date: date, branch_id, metric, segment, count, *, value=None) -> DashboardDailyMetric:
    now = utc_now()
    return DashboardDailyMetric(
        id=generate_uuid(), metric_date=metric_date, branch_id=branch_id,
        metric=str(metric), segment=segment, count=count, value=value, active=True,
        created_by=_SYSTEM, created_on=now, updated_by=_SYSTEM, updated_on=now,
    )
```

> ⚠ **Idempotencia por DELETE+INSERT en la misma tx** (`get_db` commitea al final del request): un re-run reescribe la ventana — los días cerrados quedan con el mismo valor (inmutables), el día en curso se refresca → **staleness ≤ intervalo**. **El job NUNCA propaga un 5xx**: ante un fallo de agregación marca `dashboard_refresh_state.status='error'` + `last_error` y devuelve `RefreshResult(status="error")` con 200 (Cloud Scheduler ve el 200; el panel sirve el último rollup bueno + el badge "Actualizado hace N min" crece — degrada con gracia, design §13). **sqlite (smoke)**: `func.date(...)` corre en ambos dialectos; si en F1 alguna query usara `date_trunc('week'/'month', ...)` (Postgres-only), la variante sqlite bucketiza en Python (lee filas crudas y agrupa por `.date()`). El smoke con BD limpia → `rows_written: 0`, `status: "ok"`.

### `services/report.py` — PDF/Excel server-side (lazy import)

```python
"""
Generación de reportes server-side (HU27). Lee el ROLLUP (metrics.py, NO las fuentes) y
arma un PDF (reportlab) o un Excel (openpyxl). Deps PESADAS → import LAZY dentro de cada
generador (el boot/smoke sin la dep no rompe, igual que los adaptadores LLM/calendar).
Devuelve (bytes, media_type, filename) — el ROUTER arma el StreamingResponse + Content-Disposition.
Minimiza PHI: agregados, NO nombres de pacientes (Ley 29733).
"""

from __future__ import annotations

from app.core.exceptions import BadRequestException
from app.modules.dashboards.enums import ReportFormat
from app.modules.dashboards.schemas.report import ReportRequest


async def generate_report(db, req: ReportRequest) -> tuple[bytes, str, str]:
    if req.format == ReportFormat.pdf:
        return await _generate_pdf(db, req)
    if req.format == ReportFormat.excel:
        return await _generate_excel(db, req)
    # ReportFormat ya valida en Pydantic; este guard es el backstop del contrato §8.
    raise BadRequestException(
        f"Formato de reporte no soportado: {req.format!r}", code="REPORT_FORMAT_NOT_SUPPORTED")


async def _generate_pdf(db, req: ReportRequest) -> tuple[bytes, str, str]:
    from io import BytesIO          # lazy
    from reportlab.lib.pagesizes import A4   # lazy (dep nueva)
    from reportlab.pdfgen import canvas      # lazy
    # Lee el rollup vía metrics.get_funnel/summary/distribution/leads_evolution (mismas funciones
    # que el panel), renderiza portada (clínica/rango/sede/generado-por) + KPIs + embudo + donut +
    # línea. buf = BytesIO(); ... ; return buf.getvalue(), "application/pdf", f"dashboard-{req.date_from}-{req.date_to}.pdf"
    ...


async def _generate_excel(db, req: ReportRequest) -> tuple[bytes, str, str]:
    from io import BytesIO          # lazy
    from openpyxl import Workbook   # lazy (dep nueva)
    # Una hoja KPIs + una hoja por dataset (embudo / citas por estado / leads por día), celdas
    # CRUDAS (números como números, NO strings — el usuario re-grafica). return buf.getvalue(),
    # "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"dashboard-...xlsx"
    ...
```

> ⚠ **Lazy import obligatorio** (`reportlab`/`openpyxl` son deps nuevas y pesadas): el `import` va **dentro** de `_generate_pdf`/`_generate_excel`, nunca a nivel módulo — así el boot, el smoke (que no genera reportes) y un deploy sin la dep instalada no rompen (mismo patrón que `OpenAIProvider` importa `AsyncOpenAI` dentro de `complete`, y los adaptadores de `calendar` importan `httpx` lazy). El **Excel usa números crudos** (no strings) aunque el wire de la API serialice Numeric como string — el reporte es para re-graficar, no es el wire JSON.

## Routers

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; las 4 lecturas y el report son **`POST`** (llevan `DashboardFilter` en el body, no query params); `/meta` es **`GET`**; `/internal/refresh` es **PÚBLICO** (sin RBAC), gateado por el **shared-secret** (`hmac.compare_digest`, molde `bots.verify_dispatch_secret` / ADR-012).

```python
# routers/metrics.py
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import DBSession, RequirePermission
from app.modules.dashboards.schemas.distribution import DistributionSummary
from app.modules.dashboards.schemas.filter import DashboardFilter
from app.modules.dashboards.schemas.funnel import FunnelSummary
from app.modules.dashboards.schemas.meta import DashboardMeta
from app.modules.dashboards.schemas.series import TimeSeries
from app.modules.dashboards.schemas.summary import KpiSummary
from app.modules.dashboards.services import metrics as metrics_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(tags=["dashboards"])
_VIEW = Depends(RequirePermission("DASHBOARD_VIEW"))


@router.post("/funnel", response_model=SingleResponse[FunnelSummary], dependencies=[_VIEW])
async def funnel(payload: DashboardFilter, db: DBSession) -> SingleResponse[FunnelSummary]:
    return await metrics_service.get_funnel(db, payload)


@router.post("/leads-evolution", response_model=SingleResponse[TimeSeries], dependencies=[_VIEW])
async def leads_evolution(payload: DashboardFilter, db: DBSession) -> SingleResponse[TimeSeries]:
    return await metrics_service.get_leads_evolution(db, payload)


@router.post("/appointments-distribution", response_model=SingleResponse[DistributionSummary], dependencies=[_VIEW])
async def appointments_distribution(payload: DashboardFilter, db: DBSession) -> SingleResponse[DistributionSummary]:
    return await metrics_service.get_appointments_distribution(db, payload)


@router.post("/summary", response_model=SingleResponse[KpiSummary], dependencies=[_VIEW])
async def summary(payload: DashboardFilter, db: DBSession) -> SingleResponse[KpiSummary]:
    return await metrics_service.get_summary(db, payload)


@router.get("/meta", response_model=SingleResponse[DashboardMeta], dependencies=[_VIEW])
async def meta(db: DBSession) -> SingleResponse[DashboardMeta]:
    return await metrics_service.get_meta(db)
```

```python
# routers/refresh.py — PÚBLICO, shared-secret (molde bots.verify_dispatch_secret / ADR-012)
from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.config import get_settings
from app.core.dependencies import DBSession
from app.core.exceptions import UnauthorizedException
from app.modules.dashboards.schemas.refresh import RefreshResult
from app.modules.dashboards.services import refresh as refresh_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/internal", tags=["dashboards · internal"])

_REFRESH_SECRET_HEADER = "X-Dashboard-Refresh-Secret"


async def verify_refresh_secret(
    x_dashboard_refresh_secret: Annotated[str | None, Header(alias=_REFRESH_SECRET_HEADER)] = None,
) -> None:
    """Auth del endpoint interno /internal/refresh (target Cloud Scheduler, sin RBAC): compara
    el header con DASHBOARD_REFRESH_SECRET en TIEMPO CONSTANTE (hmac.compare_digest). Un secret
    CONFIGURADO vacío → 401 SIEMPRE (nunca aceptar un header ausente contra un secret vacío; el
    boot-validator ya impide arrancar con el módulo activo y el secret vacío fuera de dev).
    Mismo primitivo que bots.verify_dispatch_secret (ADR-012)."""
    expected = get_settings().DASHBOARD_REFRESH_SECRET.strip()
    provided = (x_dashboard_refresh_secret or "").strip()
    if not expected or not hmac.compare_digest(provided, expected):
        raise UnauthorizedException(
            "Refresh no autorizado", code="DASHBOARD_REFRESH_SECRET_INVALID")


@router.post("/refresh", response_model=SingleResponse[RefreshResult],
             dependencies=[Depends(verify_refresh_secret)])
async def refresh(db: DBSession) -> SingleResponse[RefreshResult]:
    """SIN RBAC: lo autentica el shared-secret. Recomputa el rollup (ventana móvil) y devuelve
    el RefreshResult. Un fallo de agregación → status='error' dentro del 200 (NO 5xx; el job
    degrada con gracia). Cloud Scheduler lo invoca cada DASHBOARD_REFRESH_INTERVAL_MINUTES."""
    return await refresh_service.run_refresh(db)
```

```python
# routers/report.py — REPORTS_EXPORT, devuelve binario
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.dependencies import DBSession, RequirePermission
from app.modules.dashboards.schemas.report import ReportRequest
from app.modules.dashboards.services import report as report_service

router = APIRouter(tags=["dashboards · reports"])


@router.post("/report", dependencies=[Depends(RequirePermission("REPORTS_EXPORT"))])
async def report(payload: ReportRequest, db: DBSession) -> Response:
    """Genera el binario (PDF | xlsx) server-side leyendo el rollup. Devuelve Response binaria con
    Content-Disposition (un router que devuelve binario es la excepción a 'los services devuelven
    el envelope' — el binario es transporte, no payload de dominio; molde calendar.oauth_callback
    que devuelve RedirectResponse)."""
    content, media_type, filename = await report_service.generate_report(db, payload)
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

> ⚠ El `/report` y `/internal/refresh` son las **2 excepciones** a "los services devuelven el envelope": el report devuelve **binario** (`Response`) y el refresh es un endpoint de máquina; ambos son transporte. El refresh usa `UnauthorizedException` (401) no `ForbiddenException` (403) porque la spec §8 fija `DASHBOARD_REFRESH_SECRET_INVALID (401)` (a diferencia de `bots` que usa 403 `BOT_DISPATCH_UNAUTHORIZED` — aquí gana la spec).

## API contracts

Envelopes del template: `SingleResponse` `{success, data}`, error `{success, detail, code?, errors?}`. Prefijo común `/api/v1/dashboards/`. Las 4 lecturas + el report son `POST` con body `DashboardFilter`; `/meta` es `GET`; ninguna lectura pagina.

### `POST /api/v1/dashboards/funnel` — `DASHBOARD_VIEW` → `SingleResponse[FunnelSummary]`
**Request** (`DashboardFilter`):
```json
{ "date_from": "2026-06-01", "date_to": "2026-06-30", "branch_id": null, "source": null, "campaign_id": null }
```
**Response 200**:
```json
{ "success": true, "data": {
  "stages": [
    { "key": "conversations", "label": "Conversaciones", "count": 412, "rate_from_prev": null, "color": null },
    { "key": "leads", "label": "Leads", "count": 356, "rate_from_prev": 0.8641, "color": null },
    { "key": "engaged", "label": "Contactados/Interesados", "count": 241, "rate_from_prev": 0.6770, "color": null },
    { "key": "appointments", "label": "Citas agendadas", "count": 138, "rate_from_prev": 0.5726, "color": null },
    { "key": "confirmed", "label": "Citas confirmadas", "count": 96, "rate_from_prev": 0.6957, "color": null },
    { "key": "customers", "label": "Clientes", "count": 71, "rate_from_prev": 0.7396, "color": null }
  ],
  "conversion_rate": 0.2345, "total_leads": 356, "total_appointments": 138,
  "total_customers": 71, "chatbot_share": 0.58
} }
```

### `POST /api/v1/dashboards/leads-evolution` — `DASHBOARD_VIEW` → `SingleResponse[TimeSeries]`
**Request**: `DashboardFilter` (igual). **Response 200**:
```json
{ "success": true, "data": {
  "series": [
    { "key": "NUEVO", "label": "Nuevo", "color": "#9CA3AF" },
    { "key": "CONTACTADO", "label": "Contactado", "color": "#3B82F6" },
    { "key": "CITA_AGENDADA", "label": "Cita agendada", "color": "#22C55E" }
  ],
  "points": [
    { "date": "2026-06-01", "values": { "NUEVO": 12, "CONTACTADO": 5, "CITA_AGENDADA": 2 } },
    { "date": "2026-06-02", "values": { "NUEVO": 9 } }
  ]
} }
```

### `POST /api/v1/dashboards/appointments-distribution` — `DASHBOARD_VIEW` → `SingleResponse[DistributionSummary]`
**Request**: `DashboardFilter` (con `branch_id` opcional para la sede). **Response 200**:
```json
{ "success": true, "data": {
  "buckets": [
    { "code": "SCHEDULED", "label": "Agendada", "color": "#3B82F6", "count": 22 },
    { "code": "CONFIRMED", "label": "Confirmada", "color": "#06B6D4", "count": 18 },
    { "code": "ATTENDED", "label": "Atendida", "color": "#22C55E", "count": 71 },
    { "code": "NO_SHOW", "label": "No asistió", "color": "#EF4444", "count": 9 },
    { "code": "CANCELLED", "label": "Cancelada", "color": "#6B7280", "count": 12 },
    { "code": "RESCHEDULED", "label": "Reagendada", "color": "#9CA3AF", "count": 6 }
  ],
  "total": 138
} }
```

### `POST /api/v1/dashboards/summary` — `DASHBOARD_VIEW` → `SingleResponse[KpiSummary]`
**Response 200** (`bot_cost_usd` es **string**):
```json
{ "success": true, "data": {
  "conversion_rate": 0.2345, "lead_to_appt_rate": 0.3876, "confirmation_rate": 0.6957,
  "show_rate": 0.8875, "no_show_rate": 0.1125, "customer_rate": 0.7396,
  "total_conversations": 412, "conversations_bot": 239, "total_leads": 356,
  "total_appointments": 138, "total_confirmed": 96, "total_attended": 71,
  "total_customers": 71, "bot_turns": 1840, "bot_cost_usd": "12.47"
} }
```

### `GET /api/v1/dashboards/meta` — `DASHBOARD_VIEW` → `SingleResponse[DashboardMeta]`
```json
{ "success": true, "data": {
  "last_refreshed_at": "2026-06-24T15:50:00+00:00",
  "lead_statuses": [
    { "code": "NUEVO", "name": "Nuevo", "color": "#9CA3AF", "display_order": 10 },
    { "code": "CITA_AGENDADA", "name": "Cita agendada", "color": "#22C55E", "display_order": 60 }
  ],
  "appointment_statuses": [
    { "code": "SCHEDULED", "name": "Agendada", "color": "#3B82F6", "display_order": 10 },
    { "code": "ATTENDED", "name": "Atendida", "color": "#22C55E", "display_order": 50 }
  ],
  "branches": [ { "id": "b1...", "name": "Sede Miraflores" } ],
  "sources": [ "bot", "advisor", "admin" ]
} }
```

### `POST /api/v1/dashboards/report` — `REPORTS_EXPORT` → binario
**Request** (`ReportRequest` = `DashboardFilter` + `format` + `sections`):
```json
{ "date_from": "2026-06-01", "date_to": "2026-06-30", "branch_id": null,
  "format": "pdf", "sections": ["kpis", "funnel", "distribution", "evolution"] }
```
**Response 200**: cuerpo binario; headers `Content-Type: application/pdf` (o `...spreadsheetml.sheet`) + `Content-Disposition: attachment; filename="dashboard-2026-06-01-2026-06-30.pdf"`.
**Error 400** (`format` inválido): `{ "success": false, "detail": "Formato de reporte no soportado: 'csv'", "code": "REPORT_FORMAT_NOT_SUPPORTED" }`

### `POST /api/v1/dashboards/internal/refresh` — **shared-secret** (header `X-Dashboard-Refresh-Secret`) → `SingleResponse[RefreshResult]`
**Request**: sin body; header `X-Dashboard-Refresh-Secret: <DASHBOARD_REFRESH_SECRET>`. **Response 200**:
```json
{ "success": true, "data": { "refreshed_at": "2026-06-24T15:50:00+00:00", "window_days": 90, "rows_written": 1284, "status": "ok" } }
```
**Error 401** (secret inválido/ausente): `{ "success": false, "detail": "Refresh no autorizado", "code": "DASHBOARD_REFRESH_SECRET_INVALID" }`

## Códigos de error (en service, `detail` español + `code` inglés)

| Code | HTTP | Cuándo |
|---|---|---|
| `DASHBOARD_INVALID_DATE_RANGE` | 400 | `date_to < date_from` o rango > 366 días (backstop del 422 Pydantic; el code de dominio gana, §22) |
| `DASHBOARD_REFRESH_SECRET_INVALID` | 401 | header del `/internal/refresh` ausente o != `DASHBOARD_REFRESH_SECRET` (`hmac.compare_digest`) |
| `REPORT_FORMAT_NOT_SUPPORTED` | 400 | `format` != `pdf`/`excel` (backstop del enum `ReportFormat`) |

> ⚠ **Lecturas con rollup vacío → NO error**: si no hay filas en el rollup (módulo recién desplegado, job aún no corrió, rango sin datos), las lecturas devuelven `SingleResponse` con **conteos 0 / tasas 0.0 / buckets vacíos** (spec §8) — `COALESCE(sum, 0)` lo garantiza. El front muestra el estado "sin datos", no un error. El `/internal/refresh` ante un fallo de agregación devuelve `status:"error"` dentro de un **200** (no un 5xx) — el job degrada con gracia.

## Permisos (3) + subsets de rol

En `_seed-and-roles.md` + `seed.py:SEED_PERMISSIONS` (F0, forward-declarados; `_seed_role` filtra los inexistentes — se autoactivan, patrón scheduling/calendar F0). Total **120 → 123** (verificado contra `seed.py` en develop@6bf33bd: 120 codes hoy, incl. 4 de calendar).

- `MENU-DASHBOARDS` — reservado (muestra el item de nav del panel; igual que `MENU-SCHEDULING`/`MENU-CALENDAR`).
- `DASHBOARD_VIEW` — ver el panel (funnel + leads-evolution + appointments-distribution + summary + meta).
- `REPORTS_EXPORT` — generar/descargar reportes PDF/Excel (`POST /report`).

Subsets: **ADMIN** = los 3 (auto). **ASESOR** = `DASHBOARD_VIEW` + `REPORTS_EXPORT` (HU26: "Asesor o Administrador"; el `MENU-*` reservado no se asigna — el gate de nav es el permiso fino). **DOCTOR** = ninguno (su vista operativa es "Mi agenda" en `scheduling`; dashboard clínico por-doctor = diferido D1).

> El `/internal/refresh` NO lleva permiso (es público, gateado por el shared-secret); el resto del módulo va bajo `DASHBOARD_VIEW`/`REPORTS_EXPORT`.

## Migration draft — `0026_dashboard_metric` (F1)

`down_revision = "0025_calendar_connection"` (la última aplicada — `calendar` fue el módulo #9; revid **30 chars ≤ 32**). Crea las 2 tablas derivadas + el UNIQUE/índices del rollup + los **índices ADITIVOS** en las columnas temporales de las tablas fuente que el job escanea (hoy no indexadas). **Tablas NUEVAS y vacías + índices aditivos → sin riesgo de FK huérfana ni de constraint sobre datos pre-existentes** (a diferencia de la lección §20 de marketing, que agregaba un FK a una columna pre-existente; aquí no hay constraint nuevo sobre datos viejos, solo índices).

```python
"""add dashboard rollup + refresh state + source indices (módulo dashboards, Fase 1)

Revision ID: 0026_dashboard_metric
Revises: 0025_calendar_connection
Create Date: 2026-06-24 00:00:00

Crea `dashboard_daily_metric` (PK·A·T — el rollup diario, UNIQUE por grano +
índice de cobertura) + `dashboard_refresh_state` (PK·A·T — singleton de observabilidad).
Agrega índices ADITIVOS en las columnas temporales de las tablas fuente que el job de
refresh escanea por fecha (hoy no indexadas): lead_status_history.changed_at,
conversation.opened_at, person.created_on, person_customer_status.became_customer_at.
appointment YA tiene (branch_id, scheduled_for, status_id) → no se toca. Tablas nuevas
vacías + índices aditivos → sin FK huérfana ni constraint sobre datos pre-existentes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_dashboard_metric"
down_revision: str | None = "0025_calendar_connection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── dashboard_daily_metric (PK·A·T, sin SoftDelete) ──
    op.create_table(
        "dashboard_daily_metric",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("branch_id", sa.String(length=36), nullable=True),  # FK lógica (ADR-009), sin constraint
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("segment", sa.String(length=60), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_unique_constraint(
        "uq_dashboard_daily_metric_grain",
        "dashboard_daily_metric",
        ["metric_date", "branch_id", "metric", "segment"],
    )
    op.create_index(
        "ix_dashboard_daily_metric_lookup",
        "dashboard_daily_metric",
        ["metric", "metric_date", "branch_id"],
    )

    # ── dashboard_refresh_state (PK·A·T, singleton) ──
    op.create_table(
        "dashboard_refresh_state",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )

    # ── Índices ADITIVOS en las tablas fuente (acelerar el escaneo por fecha del job) ──
    op.create_index("ix_lead_status_history_changed_at", "lead_status_history", ["changed_at"])
    op.create_index("ix_conversation_opened_at", "conversation", ["opened_at"])
    op.create_index("ix_person_created_on", "person", ["created_on"])
    op.create_index(
        "ix_person_customer_status_became_at", "person_customer_status", ["became_customer_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_person_customer_status_became_at", table_name="person_customer_status")
    op.drop_index("ix_person_created_on", table_name="person")
    op.drop_index("ix_conversation_opened_at", table_name="conversation")
    op.drop_index("ix_lead_status_history_changed_at", table_name="lead_status_history")
    op.drop_table("dashboard_refresh_state")
    op.drop_index("ix_dashboard_daily_metric_lookup", table_name="dashboard_daily_metric")
    op.drop_constraint("uq_dashboard_daily_metric_grain", "dashboard_daily_metric", type_="unique")
    op.drop_table("dashboard_daily_metric")
```

> ⚠ **F0 NO lleva migración** (perms + nav + Settings + boot-validator + paquete inerte). **F2 y F3 NO llevan migración** (panel frontend + reportes server-side son código puro — la lectura es on-demand sobre el rollup, los reportes leen el rollup). La única migración del módulo es `0026` (F1). El índice en `person.created_on` se agrega aunque `customers_new` use `person_customer_status.became_customer_at` — es para un futuro "leads por `person.created_on`" + lo nombra la spec §1; si en F1 se confirma que no se usa, **omitirlo** (índice innecesario = costo de escritura sin lectura). **Decidir en F1**.

## Settings (config.py) + boot-validator + deploy

Agregar a `app/core/config.py:Settings` (tras el bloque de `calendar`):

```python
# ── Dashboards (módulo #10, ADR-015) ──
# Capa de agregación materializada (rollup diario refrescado por Cloud Scheduler). El refresh
# se dispara vía POST /dashboards/internal/refresh con un SHARED-SECRET (header
# X-Dashboard-Refresh-Secret, hmac.compare_digest — molde BOT_DISPATCH_SECRET/ADR-012). El
# secret va por --set-secrets de Cloud Run (medisage-dashboard-refresh-secret-{qa,prod}).
# Default vacío → el módulo no puede refrescar (las lecturas igual sirven el rollup existente o 0).
DASHBOARD_REFRESH_SECRET: str = ""                 # Secret Manager
DASHBOARD_REFRESH_INTERVAL_MINUTES: int = 10       # cadencia del Cloud Scheduler (informativo p/ el front)
DASHBOARD_REFRESH_WINDOW_DAYS: int = 90            # ventana móvil que el job recomputa
```

**Boot-validator** `_enforce_dashboard_refresh_secret` (espejo exacto de `_enforce_bot_dispatch_secret`):

```python
@model_validator(mode="after")
def _enforce_dashboard_refresh_secret(self) -> Settings:
    """Si el módulo dashboards está activo (su Cloud Scheduler apunta al endpoint interno),
    fuera de `dev` el /dashboards/internal/refresh DEBE tener un DASHBOARD_REFRESH_SECRET real:
    es la ÚNICA barrera entre internet y el recómputo del rollup (el servicio es público). Falla
    RUIDOSA al boot ante un secret vacío/corto en vez de aceptar refreshes sin auth o
    rechazarlos en silencio (lección operativa: nada que solo falle en prod). Se gatea por
    'módulo activo' = un INTERVAL/WINDOW configurado (proxy de que el Scheduler existe)."""
    if self.ENV_NAME == "dev":
        return self
    # El módulo se considera 'desplegado con refresh' fuera de dev → exigir el secret.
    if len(self.DASHBOARD_REFRESH_SECRET.strip()) < _MIN_SECRET_LEN:
        raise ValueError(
            "dashboards module is deployed but DASHBOARD_REFRESH_SECRET is missing or too short "
            f"(need >= {_MIN_SECRET_LEN} chars) for ENV_NAME={self.ENV_NAME!r}. Set the "
            "per-environment secret (generate with: python -c "
            "'import secrets; print(secrets.token_urlsafe(48))')."
        )
    return self
```

> ⚠ **El gate del validator**: `bots` se gatea por `CLOUD_TASKS_QUEUE` seteado (proxy de "auto-path habilitado"). `dashboards` no tiene un equivalente obvio — el refresh es intrínseco al módulo. La opción del doc: **exigir el secret fuera de `dev` sin más gate** (el módulo siempre se despliega con su Scheduler). Alternativa: agregar un `DASHBOARD_REFRESH_ENABLED: bool` como gate explícito (espeja `CLOUD_TASKS_QUEUE`). **Decidir en F0**: el doc recomienda el gate simple (sin flag extra), porque el módulo no es opcional como el auto-path del bot. `_MIN_SECRET_LEN` es la misma constante del módulo (`32`, usada por `_enforce_bot_dispatch_secret`).

- **Defaults vacíos → el smoke (ENV=dev) NO valida el secret** (ningún test arranca un refresh real con secret). No hace falta tocar `conftest.py` salvo que un test setee `ENV_NAME != dev`.
- **Deploy (lección §9/§11)**: agregar `DASHBOARD_REFRESH_INTERVAL_MINUTES`/`DASHBOARD_REFRESH_WINDOW_DAYS` a `--set-env-vars` y `DASHBOARD_REFRESH_SECRET` a `--set-secrets` de **AMBOS** workflows `deploy-backend-{qa,prod}.yml`. Secret nuevo: `medisage-dashboard-refresh-secret-{qa,prod}` en Secret Manager.
- **Infra Cloud Scheduler**: provisionar un job cron (cada `DASHBOARD_REFRESH_INTERVAL_MINUTES`) → `POST {SERVICE_BASE_URL}/api/v1/dashboards/internal/refresh` con el header `X-Dashboard-Refresh-Secret: <secret>`. Molde ADR-012 (el job de Cloud Scheduler reemplaza a Cloud Tasks: no necesita encolar, es un disparo periódico). Provisionar **antes** del deploy que lo referencia.

## Fases (resumen backend)

- **F0 Prep** (sin migr): 3 perms `MENU-DASHBOARDS`/`DASHBOARD_VIEW`/`REPORTS_EXPORT` + subsets de rol (forward-declarados) en seed; Settings (3 vars + `_enforce_dashboard_refresh_secret`); `endpoints.ts` bloque `DASHBOARDS` + `types/dashboards.types.ts` espejo + nav (panel/reportes + íconos); paquete backend **INERTE** (NO registrado en `modules/__init__.py`/`main.py`). Smoke: login admin + perm count (123) + rutas `/dashboards/*` → 404. Molde scheduling/calendar F0.
- **F1 Capa de agregación + lectura** — `0026_dashboard_metric`: modelos + `enums.py` + `repositories/dashboard_metric` (SUM rollup) + `repositories/source_aggregation` (agrega fuentes, `func.date`) + `repositories/dashboard_refresh_state` (singleton) + `services/catalog` (resolución por code) + `services/metrics` (funnel/leads-evolution/appointments-distribution/summary/meta) + `services/refresh` (recompute + DELETE+INSERT idempotente) + routers (metrics + refresh) + registrar el módulo + Cloud Scheduler + índices aditivos. Smoke: las 5 lecturas con BD limpia → conteos 0 (NO error); `/internal/refresh` con el secret correcto → `rows_written:0, status:ok`; con secret malo → 401; rango inválido → 400 `DASHBOARD_INVALID_DATE_RANGE`. **QA E2E real** (sembrar/usar data real en Postgres → refrescar → leer el funnel/donut/línea; verificar `func.date` corta en frontera UTC).
- **F2 Panel (frontend)** (sin migr): ver [`frontend.md`](frontend.md)/[`ui.md`](ui.md). `/dashboard` + Fluent Charts + filtros + React Query (`refetchInterval`) + Lighthouse. Backend intacto.
- **F3 Reportes** (sin migr): `services/report` (PDF `reportlab` + Excel `openpyxl`, lazy import) + `routers/report` (`POST /report` → binario) + página `/dashboard/reportes`. Deps nuevas (back): la lib PDF + `openpyxl` en `pyproject.toml`. Smoke: `/report` con BD limpia + `format:pdf` → 200 binario (PDF de ceros, válido); `format:csv` → 400 `REPORT_FORMAT_NOT_SUPPORTED`.
- **Diferidas (D1–D4)**: D1 dashboard por-doctor/clínico; D2 métricas de mensajes desde Firestore (read-model, ADR-011); D3 caché distribuida (Redis/Memorystore) + particionado del rollup; D4 cómputo on-the-fly del día en curso (real-time estricto) + tendencias/forecast. **Documentadas como roadmap, NO construir.**

## Notas de implementación / gotchas (spec §13 — respetar)

- **Stock vs flujo** (`person_lead_status` soft-deletea al estado final): el "stock vivo" NO contiene leads ganados/perdidos → los conteos del embudo POR FLUJO se sacan de `lead_status_history` (append-only, inmutable, sin SoftDelete), NO del stock. `leads_created` = `from_lead_status_id IS NULL`; `lead_stage` = por `to_lead_status_id`.
- **`APPOINTMENT_BOOKED`/`APPOINTMENT_CANCELLED` NO se emiten** (están en el enum `ActivityType` de crm pero ningún flujo los inserta) → NUNCA contar citas por el timeline polimórfico; contar por `appointment.status_id` + filas de `appointment` (que es lo que hace `appointments_by_day`).
- **Mensajes en Firestore** (ADR-011): "nº de mensajes" NO es consultable en SQL. Proxies: nº de conversaciones (`conversations`), turnos del bot (`bot_turns`), recencia (`conversation.last_message_at`). Agregar mensajes desde Firestore = diferido D2.
- **`branch_id` solo en `appointment`**: el filtro por sede es exacto de la etapa "cita" en adelante; las etapas previas (conversaciones, leads, clientes, bot) son a nivel CLÍNICA (`branch_id=NULL` en el rollup). `metrics.get_funnel` solo pasa `branch_id` a `appointments`/`appointments_source`; el front etiqueta el caveat en la UI.
- **`RESCHEDULED` doble-conteo**: el reagendamiento crea una cita HIJA (`previous_appointment_id`) → `metrics` EXCLUYE `RESCHEDULED` del agregado "agendadas" del embudo (`appt_total`); el donut SÍ la muestra como estado-actual (cuenta filas por `status_id`, no transiciones → no doble-cuenta en el donut).
- **`date_trunc` Postgres-only**: el bucketing por DÍA usa `func.date(col)` (compila en Postgres y sqlite → corre idéntico en el smoke). Solo si se usara `date_trunc('week'/'month', ...)` (Postgres-only) habría que bucketizar en Python en el smoke. Verificar que `func.date` sobre `timestamptz` corta en frontera UTC (= `metric_date`).
- **`value` monetario nullable → `COALESCE`**: `bot_cost.value = SUM(COALESCE(cost_estimated_usd, 0))` y `count = SUM(COALESCE(tokens_in,0)+COALESCE(tokens_out,0))`; las lecturas `coalesce(sum, 0)` para no devolver NULL con rollup vacío. `Numeric` serializa como STRING en el wire (`bot_cost_usd`).
- **Resolver estados por code/flags, NO id hardcodeado** (ADR-008): el rollup persiste el `code` (no el uuid) en `segment` (JOIN al catálogo en el refresh); `metrics`/`catalog` descubren el code "won" por flag `is_won`, no por el literal `"CITA_AGENDADA"`. Único punto que enumera codes: `ENGAGED_LEAD_CODES` (no hay flag "engaged").
- **`UNIQUE` con columnas nullable → DELETE+INSERT, no `ON CONFLICT`**: `branch_id`/`segment` son nullable → `NULL != NULL` en el UNIQUE de Postgres → `ON CONFLICT` no dispara para métricas de clínica/escalares. La idempotencia del refresh es `delete_window` + `db.add_all` en la misma tx.
- **El job NUNCA propaga 5xx**: un fallo de agregación marca `dashboard_refresh_state.status='error'` + `last_error` y devuelve `RefreshResult(status="error")` con 200; el panel sirve el último rollup bueno (degrada con gracia, design §13).
- **Lazy import de `reportlab`/`openpyxl`** (F3): dentro de cada generador, nunca a nivel módulo (el boot/smoke/deploy sin la dep no rompe; molde adaptadores LLM/calendar).
- **`import` MODEL de otro módulo para un read es cycle-safe** (lección §22): `source_aggregation` importa `Conversation`/`LeadStatusHistory`/`Appointment`/`BotEvent`/`PersonCustomerStatus`/`LeadStatus`/`AppointmentStatus` (models leaf, sin ciclo de vuelta a dashboards).
- **El refresh secret es 401 (no 403)**: la spec §8 fija `DASHBOARD_REFRESH_SECRET_INVALID (401)` → `UnauthorizedException` (diverge de `bots` que usa 403; gana la spec).
