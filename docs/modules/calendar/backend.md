# Módulo `calendar` — Backend deep-dive

> **Última actualización**: 2026-06-22
> **Audiencia**: developer implementando `backend/app/modules/calendar/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview del módulo), [`design.md`](design.md) (arquitectura + flujos + roadmap), [`../../../backend/CLAUDE.md`](../../../backend/CLAUDE.md) (patrones del template), [`ADR-014`](../../decisions/ADR-014-external-calendar-integration.md) (la decisión: adaptador agnóstico + proveedores nativos + Fase 1 = lectura informativa a nivel clínica), y los ADRs **reutilizados**: [`ADR-005`](../../decisions/ADR-005-agnostic-bot-engine.md) (el molde del adaptador `_PROVIDER_ADAPTERS`), [`ADR-010`](../../decisions/ADR-010-runtime-secret-resolution.md) (secreto por-cuenta en Secret Manager, que se **extiende** con escritura) y [`ADR-012`](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md) (Cloud Tasks — solo la fase de **sync** futura). Deep-dives molde: [`../scheduling/backend.md`](../scheduling/backend.md) (la grilla + `_as_utc` + el `busy` hook donde engancharía el modo bloqueante futuro) y [`../bots/backend.md`](../bots/backend.md) (el adaptador de providers + el `engine_factory`).

> **Contrato autoritativo**: este doc respeta la **spec compartida** de `calendar` (entidades, campos, endpoints, permisos, códigos de error, fases). Si algo aquí discrepa de la spec o de [`README.md`](README.md)/[`ui.md`](ui.md)/[`frontend.md`](frontend.md), **gana la spec** y hay que corregir este doc.

> **Convenciones heredadas de los 8 módulos shipped** (repetidas para que el doc se lea solo):
>
> 1. **`PUT` para updates/replaces completos** (no `PATCH`).
> 2. **`/active` (o `/calendars`, `/options`) devuelve lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`).
> 3. Services = **módulos de funciones** (no clases); lanzar excepciones de dominio (`NotFoundException`, `ConflictException`, `BadRequestException`, `ForbiddenException`) — **nunca `HTTPException`**; `actor_id` explícito desde el router; reload-via-`get_full` tras create/update (relaciones `lazy="raise"`); `BaseRepository` filtra `deleted_at IS NULL`; `ALLOWED_FIELDS` whitelist estricta (los campos **denormalizados NO** son server-sortable/filterable — lección hotfix `cd10c78` de `staff`).
> 4. **`detail` de dominio en español, `code` en inglés**; mensajes de validators Pydantic en inglés (el front re-valida con Zod). UI 100% español.
> 5. Envelopes del template: `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data:{items,total,skip,limit}}`), lista cruda en `/active`/`/calendars`, error `{success:false, detail, code?, errors?}`.
> 6. **Migraciones manuales numeradas**, revid **≤ 32 chars**, `down_revision` encadenado. `calendar` arranca en `0025` (`down_revision="0024_marketing_promotion_usage"`, la última aplicada — `marketing` fue el módulo #8).
> 7. Patrón **audit users**: `created_by`/`updated_by` explícitos; `*_user: UserAuditInfo | None` hidratado vía `user_repository.get_audit_info_map` batch (sin N+1).
> 8. **TZ**: cualquier `new Date()`/now que afecte render = client-only; los eventos externos llegan como **instantes** RFC3339 → normalizar con `_as_utc` (mismo helper que [`scheduling/services/availability.py`](../../../backend/app/modules/scheduling/services/availability.py)); el front los ubica en **hora local del navegador** con los helpers `calendarWeek.ts`, igual que las citas de la grilla shippeada (render de toda la grilla en la TZ de la sede = mejora diferida conjunta).

`calendar` es el **módulo #9** de medisage (el primero tras los 8 que cerraron medisage). Integra **calendarios externos agnósticos al proveedor** (Google Calendar + Microsoft Outlook ahora; un 3ro vía CalDAV diferido), configurables desde la **vista de configuración de la clínica**. Cierra **HU43** y la incoherencia de la tesis. **Alcance Fase 1 (NO re-litigar):** solo **PULL**, **INFORMATIVO** (overlay no-bloqueante que **NO toca `scheduling.compute_available_slots`** ni los invariantes de booking), nivel **CLÍNICA** (una/pocas conexiones OAuth + N `CalendarSource` mapeando calendarios→sedes), **detalle del evento** (título + horario), proveedores **nativos** (Google API + Microsoft Graph) vía `httpx.AsyncClient` (NO el SDK sync de Google). Depende de `clinic` (`Branch` — destino del mapeo + `Branch.timezone` para el render) y `admin` (audit + RBAC). Reutiliza `app.core.secrets` (ADR-010, **extendido con escritura**), `app.core.config.Settings` y el molde del adaptador de `bots` (ADR-005).

## Estructura de archivos a crear

```
backend/app/modules/calendar/
├── __init__.py
├── enums.py                            # CalendarProvider (google|microsoft) + ConnectionStatus
├── models/
│   ├── __init__.py                     # importa los modelos (registro en Base.metadata)
│   ├── calendar_connection.py
│   └── calendar_source.py
├── schemas/
│   ├── __init__.py
│   ├── connection.py                   # CalendarConnection* (Item/Detail) + OAuthStartResponse + CalendarProviderOption
│   ├── source.py                       # CalendarSource* (Item/Create) + CalendarSourcesReplace + ExternalCalendarOption
│   └── external_event.py               # ExternalEventItem + ExternalEventsResponse (+ SourceHealth)
├── repositories/
│   ├── __init__.py
│   ├── calendar_connection.py          # get_by_provider_email, list (con sources_count), get_full
│   └── calendar_source.py              # list_for_connection, list_enabled_for_branch, replace_for_connection
├── services/
│   ├── __init__.py
│   ├── oauth.py                        # build_start_url (state firmado) + handle_callback (exchange + secrets.put + crea conexión)
│   ├── connection.py                   # list/get/disconnect + list_external_calendars (live)
│   ├── source.py                       # replace_sources (bulk REPLACE atómico, valida branch_id)
│   ├── external_read.py                # read_external_events (best-effort, NUNCA 5xx) + _resolve_creds (refresh al vuelo)
│   └── providers/
│       ├── __init__.py                 # _CALENDAR_ADAPTERS + get_adapter(provider) (molde _PROVIDER_ADAPTERS)
│       ├── base.py                     # dataclasses Credentials/ExternalCalendar/ExternalEvent + _CalendarAdapter Protocol
│       ├── google.py                   # GoogleCalendarAdapter (httpx async)
│       └── microsoft.py                # MicrosoftGraphAdapter (httpx async, Entra ID)
└── routers/
    ├── __init__.py                     # aggregator: prefix="/calendar"
    ├── oauth.py                        # /oauth/{provider}/start (RBAC) + /oauth/{provider}/callback (PÚBLICO, 302)
    ├── connection.py                   # /connections/list, /connections/{id}, DELETE, /{id}/calendars
    ├── source.py                       # PUT /connections/{id}/sources (replace)
    └── external_event.py              # GET /external-events (overlay)
```

> **No hay `models/associations.py`**: `calendar` no introduce M:N nuevas. `CalendarSource` es una entidad propia (PK, mixins, `active`, CRUD-eable vía el replace) con FK a `calendar_connection` y a `clinic.branch` — no una `Table()` de asociación.

> **No hay `bot_facade.py`**: el bot NO consume `calendar` en Fase 1 (la lectura externa es de UI/grilla, no una tool). El gancho del bot (un `list_busy`/aviso) es de la fase **bloqueante diferida**, no de F1/F2.

Registrar el módulo en `app/modules/__init__.py` (para que Alembic y los `relationship(...)` por string lo vean) — **en F1, NO en F0** (en F0 el paquete es INERTE):

```python
from app.modules import (  # noqa: F401
    admin, bots, calendar, catalog, clinic, conversations, crm, marketing, scheduling, staff,
)
```

Y registrar el aggregator en `app/main.py` (un solo `include_router`, como el resto):

```python
from app.modules.calendar.routers import router as calendar_router

app.include_router(calendar_router)  # prefix="/api/v1" + "/calendar" interno
```

El aggregator `routers/__init__.py` replica el patrón de `scheduling/routers/__init__.py`:

```python
"""
Agrega los sub-routers de calendar bajo un prefijo. `main.py` incluye este `router`
una vez. El orden de declaración importa DENTRO de cada sub-router (rutas estáticas
antes de /{id}); el orden del aggregator es informativo, salvo que las rutas estáticas
(/oauth/..., /connections/list, /external-events) deben quedar ANTES de /connections/{id}.
"""

from fastapi import APIRouter

from app.modules.calendar.routers.connection import router as connection_router
from app.modules.calendar.routers.external_event import router as external_event_router
from app.modules.calendar.routers.oauth import router as oauth_router
from app.modules.calendar.routers.source import router as source_router

router = APIRouter(prefix="/calendar")
router.include_router(oauth_router)           # /oauth/{provider}/start, /oauth/{provider}/callback
router.include_router(external_event_router)  # /external-events
router.include_router(connection_router)      # /connections/* (incl. /{id}, /{id}/calendars)
router.include_router(source_router)          # PUT /connections/{id}/sources

__all__ = ["router"]
```

> ⚠ Orden de rutas: las **estáticas** (`/oauth/google/start`, `/connections/list`, `/external-events`) van **antes** de la dinámica `/connections/{id}` para que un segmento literal no lo capture la ruta paramétrica (misma regla que `scheduling`). El `source_router` monta `PUT /connections/{id}/sources` — al ser un sufijo literal tras `{id}` no colisiona, pero se incluye después de `connection_router` por claridad.

## Enums — `enums.py` (en código, NO en BD)

`CalendarProvider`/`ConnectionStatus` son contratos estables del código (NO catálogos en BD — a diferencia de `appointment_status`). Las columnas `calendar_connection.provider`/`.status` son `varchar` planas; Pydantic valida contra el enum, la BD almacena el slug.

```python
"""
Calendar enums (code-level value sets, NO DB catalogs).
- CalendarProvider: el proveedor del adaptador agnóstico (molde bots.BotProvider).
  `caldav` queda RESERVADO (3er proveedor diferido, B4) — NO seedeado ni usado en Fase 1.
- ConnectionStatus: salud de una CalendarConnection. `needs_reauth` lo setea el refresh
  cuando el provider devuelve `invalid_grant` (revocación) → la UI muestra "Reconectar".
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
```

> El value `"caldav"` se deja **comentado** (no es un miembro vivo): seedearlo o aceptarlo en `get_adapter` sin un `CalDavAdapter` real lanzaría `CALENDAR_PROVIDER_NOT_SUPPORTED` — está bien que no exista todavía.

## Models — SQLAlchemy 2.0

**Mixins** (de `app.shared.base_model`): `PrimaryKeyMixin` (`id`), `ActiveMixin` (`active`), `SoftDeleteMixin` (`deleted_at`), `TimestampMixin` (`created_on`/`created_by`/`updated_on`/`updated_by`). **Ambas entidades llevan los 4 mixins** (`PK·A·SD·T`): la conexión/source se pausa con `active` (expuesto como `is_active`/`is_enabled`) y se desconecta/elimina con `deleted_at` (SD).

> ⚠ **`active` reusado como flag de negocio** (precedente `bots.BotConfigurationVersion`): `CalendarConnection.active` = "pausa manual de la conexión entera" (expuesto `is_active`); `CalendarSource.active` = "habilitado para lectura" (expuesto **`is_enabled`** en el schema). **NO** se agrega una 2ª columna booleana — el mixin `ActiveMixin` ya provee `active`.

### `models/calendar_connection.py` — tabla `calendar_connection` — PK·A·SD·T

Una cuenta OAuth externa conectada a nivel CLÍNICA (típicamente 1-2 filas). **Los tokens NO viven aquí** (`secret_name` apunta a Secret Manager).

```python
"""
CalendarConnection = una cuenta OAuth de la clínica (Google/Microsoft). Típicamente
1-2 filas (la cuenta de Google de la clínica + la de Outlook). Los TOKENS NO están
aquí: `secret_name` apunta al secreto `medisage-calendar-{id}-{env}` en Secret Manager
con el JSON {access_token, refresh_token, expiry, scopes} (ADR-010 extendido).

`status` (ConnectionStatus) da salud: `needs_reauth` cuando el refresh devuelve
`invalid_grant`. `active` (ActiveMixin, expuesto is_active) = pausa manual; deleted_at
(SD) = desconectar. UNIQUE PARCIAL (provider, account_email) WHERE deleted_at IS NULL:
no conectar 2 veces la misma cuenta viva; tras desconectar, el par se libera.

`sources` 1:N con lazy="raise" (se carga con selectinload en el detalle, nunca por
accidente — N+1 ruidoso). FK cross-módulo a branch vive en CalendarSource, no aquí.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.calendar.models.calendar_source import CalendarSource


class CalendarConnection(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "calendar_connection"
    __table_args__ = (
        # UNIQUE PARCIAL: (provider, account_email) VIVA es única (single-tenant).
        # Tras soft-delete el par se libera para re-conectar. Dialect-agnóstico
        # (postgresql_where + sqlite_where) para que el smoke (create_all en sqlite)
        # reproduzca el índice parcial — molde conversations.ChannelAccount.
        Index(
            "uq_calendar_connection_provider_email",
            "provider",
            "account_email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    # CalendarProvider value (google|microsoft).
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Identidad de la cuenta (de Google userinfo / Graph /me).
    account_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Etiqueta amigable (default = account_email, resuelto en el service si llega NULL).
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Puntero a Secret Manager (medisage-calendar-{id}-{env}). NUNCA el token en sí.
    secret_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # ConnectionStatus value; default connected al crear.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="connected"
    )
    # Scopes concedidos (auditoría, space-separated).
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Última validación/refresh OK (observabilidad UI "Última revisión: hace N").
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Último error de refresh/list (observabilidad, NO bloquea).
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 1:N. lazy="raise": el detalle usa selectinload(CalendarConnection.sources).
    sources: Mapped[list[CalendarSource]] = relationship(
        back_populates="connection", lazy="raise", cascade="all, delete-orphan"
    )
```

### `models/calendar_source.py` — tabla `calendar_source` — PK·A·SD·T

Un calendario concreto dentro de una conexión, mapeado a una sede.

```python
"""
CalendarSource = un calendario concreto de una conexión, mapeado a una sede (Branch).
El conjunto de sources con is_enabled=true (active=true) ES "el grupo de calendarios
de la clínica" (resuelve la Q1 del design: una conexión global + N sources por sede).

`branch_id` NULLABLE = "todas las sedes" (decisión LOCKED #3). FK a clinic.branch con
ondelete RESTRICT (backstop hard-delete: no se puede borrar una sede con sources vivos).
`is_enabled` (flag de lectura) = ActiveMixin.active expuesto en el schema (NO 2ª columna).

UNIQUE PARCIAL (connection_id, external_calendar_id) WHERE deleted_at IS NULL: un mismo
calendario externo no se mapea dos veces vivo en la misma conexión; el bulk-replace
soft-deletea los viejos antes de insertar el set nuevo, así el par se libera.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.calendar.models.calendar_connection import CalendarConnection


class CalendarSource(
    PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base
):
    __tablename__ = "calendar_source"
    __table_args__ = (
        Index(
            "uq_calendar_source_connection_external",
            "connection_id",
            "external_calendar_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_calendar_source_branch", "branch_id"),
    )

    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("calendar_connection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Id del calendario en el proveedor.
    external_calendar_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Denorm del nombre del calendario (para mostrar sin re-llamar al provider).
    external_calendar_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK cross-módulo a clinic.branch. NULLABLE = "todas las sedes". RESTRICT: la tabla
    # branch existe en prod (ADR-009 NO aplica) → FK real; sin relationship ORM cross-módulo.
    branch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("branch.id", ondelete="RESTRICT"), nullable=True
    )

    connection: Mapped[CalendarConnection] = relationship(
        back_populates="sources", lazy="raise"
    )
```

> ⚠ **FK a `branch` es real** (la tabla existe en prod, igual que `scheduling.appointment` apunta a `branch`): NO se declara `relationship` ORM cross-módulo — `branch_name` se denormaliza por id + batch map (`clinic.branch_repository.get_by_ids`), igual que `scheduling` resuelve `branch_name`. La FK es `ondelete="RESTRICT"`: borrar una sede con sources vivos lanzaría a nivel BD; el service lo previene revalidando `branch_id` antes de insertar (`BRANCH_NOT_FOUND`, lección §20/§22).

### `models/__init__.py`

```python
"""
Importar los modelos acá los registra en Base.metadata antes de que Alembic lea el
esquema y antes de resolver los relationship() por string. Orden: connection antes
que source (source FK→connection).
"""

from app.modules.calendar.models.calendar_connection import CalendarConnection
from app.modules.calendar.models.calendar_source import CalendarSource

__all__ = ["CalendarConnection", "CalendarSource"]
```

**Lazy strategy**: `CalendarConnection.sources` y `CalendarSource.connection` son `lazy="raise"`; el detalle de conexión carga `sources` con `selectinload(CalendarConnection.sources)` explícito. No hay relationship ORM hacia `clinic.Branch` (se resuelve por id + batch map). Cero N+1 silencioso.

## El adaptador agnóstico `CalendarProvider` (molde ADR-005)

Calcado del molde de bots ([`bots/services/engine/embedded.py:69`](../../../backend/app/modules/bots/services/engine/embedded.py)): `_PROVIDER_ADAPTERS: dict[BotProvider, Callable[[str], _ProviderAdapter]]` + un `Protocol` común + import lazy del SDK. Acá el dict es `_CALENDAR_ADAPTERS`, el `Protocol` es `_CalendarAdapter`, y el "SDK" es **`httpx.AsyncClient`** (NO el SDK sync de Google `google-api-python-client`, que es bloqueante y rompería el event loop). `httpx` ya es dep del backend (verificar `pyproject.toml`); el import va lazy dentro de cada método igual que `OpenAIProvider` importa `AsyncOpenAI` dentro de `complete`.

### `services/providers/base.py` — tipos neutros + Protocol

```python
"""
Tipos NEUTROS del adaptador de calendario (molde del ProviderResult neutro de bots).
El motor de calendar habla con estos dataclasses, no con Google/Microsoft. Todos los
datetimes son UTC-aware (los eventos del provider llegan como instantes RFC3339 con
offset → se normalizan con _as_utc, igual que availability.py).

La superficie de Fase 1 son 5 métodos; la superficie FUTURA (get_busy/push/watch) se
documenta en el Protocol comentada para fijar el contrato sin implementarla (B1-B3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class Credentials:
    """Lo que vive en Secret Manager (JSON). expiry es UTC-aware."""

    access_token: str
    refresh_token: str | None
    expiry: datetime
    scopes: list[str]


@dataclass
class ExternalCalendar:
    """Un calendario del proveedor (para la UI de mapeo)."""

    id: str  # external_calendar_id
    name: str
    primary: bool


@dataclass
class ExternalEvent:
    """Un evento leído (overlay, Fase 1). Detalle = título + horario (Q3). Instantes UTC."""

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool


class _CalendarAdapter(Protocol):
    """Contrato común de los adaptadores (GoogleCalendarAdapter / MicrosoftGraphAdapter).
    Construido con el client_id/secret del provider (Settings, global por entorno)."""

    def build_auth_url(self, *, state: str, redirect_uri: str) -> str:
        """URL de consentimiento OAuth (sin llamada de red). Incluye el `state` firmado."""
        ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> Credentials:
        """Authorization Code → tokens. + lee la identidad (account_email) si el provider la expone."""
        ...

    async def refresh(self, creds: Credentials) -> Credentials:
        """refresh_token → nuevo access_token (+ expiry). invalid_grant → el caller marca needs_reauth."""
        ...

    async def list_calendars(self, creds: Credentials) -> list[ExternalCalendar]:
        """Los calendarios de la cuenta (para mapear a sedes)."""
        ...

    async def list_events(
        self,
        creds: Credentials,
        *,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[ExternalEvent]:
        """Eventos de UN calendario en [time_min, time_max) (instantes UTC). Fase 2."""
        ...

    # ── Superficie FUTURA (documentada, NO implementada en Fase 1) ──
    # async def get_busy(self, creds, *, calendar_ids, time_min, time_max) -> list[tuple[datetime, datetime]]:
    #     """B1 modo BLOQUEANTE: free/busy opaco → alimenta el `busy` de compute_available_slots
    #     (extiende ADR-006). Google freebusy.query / Graph getSchedule. ⚠ getSchedule NO soporta
    #     cuentas Outlook.com personales (decisión LOCKED #6)."""
    # async def push_event(self, creds, *, calendar_id, event) -> str: ...   # B2 push (events.insert)
    # async def update_event(self, creds, *, calendar_id, external_id, event) -> None: ...  # B2
    # async def delete_event(self, creds, *, calendar_id, external_id) -> None: ...         # B2
    # async def watch(self, creds, *, calendar_id, callback_url) -> WatchChannel: ...       # B3 sync
    # async def unwatch(self, creds, *, channel) -> None: ...                               # B3
    # async def get_changes(self, creds, *, calendar_id, sync_token) -> ChangeSet: ...      # B3 delta
```

> ⚠ Los métodos futuros viven **comentados** en el Protocol (no como `raise NotImplementedError` en las clases): así el contrato queda fijado para B1-B3 sin que un adaptador de Fase 1 deba stubear nada, y `mypy --strict` no exige implementarlos. Los nombres (`get_busy`/`push_event`/`watch`) son el vocabulario de la interfaz `Calendar` de Cal.com + el modo bloqueante de ADR-006.

### `services/providers/google.py` — `GoogleCalendarAdapter` (httpx async)

```python
"""
GoogleCalendarAdapter sobre Google Calendar API v3 + OAuth2, vía httpx.AsyncClient
(NO el SDK sync google-api-python-client). client_id/secret = Settings (global por
entorno). Scope `calendar.readonly` (DETALLE = sensitive → verificación OAuth de Google
antes de GA). Auth con access_type=offline + prompt=consent (para garantizar el
refresh_token). ⚠ Gotcha: la app OAuth en estado "Testing" emite refresh tokens de 7
DÍAS → publicar "In production" antes de confiar en el almacenamiento durable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.core.config import get_settings
from app.modules.calendar.services.providers.base import (
    Credentials,
    ExternalCalendar,
    ExternalEvent,
)
from app.shared.utils import utc_now

_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_BASE = "https://www.googleapis.com/calendar/v3"
_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "https://www.googleapis.com/auth/calendar.readonly openid email"


class GoogleCalendarAdapter:
    def __init__(self, _model: str = "") -> None:
        # firma (str) para igualar el molde _PROVIDER_ADAPTERS[..](arg); el arg es ignorado.
        settings = get_settings()
        self._client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        self._client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET

    def build_auth_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "access_type": "offline",   # ← refresh_token
            "prompt": "consent",        # ← fuerza el refresh aun si ya consintió
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{_AUTH_BASE}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> Credentials:
        import httpx  # lazy

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()      # el caller traduce a CALENDAR_OAUTH_EXCHANGE_FAILED
            tok = resp.json()
            # identidad de la cuenta (account_email) vía userinfo con el access_token nuevo.
            me = await client.get(
                _USERINFO, headers={"Authorization": f"Bearer {tok['access_token']}"}
            )
            email = me.json().get("email", "") if me.status_code == 200 else ""
        return Credentials(
            access_token=tok["access_token"],
            refresh_token=tok.get("refresh_token"),
            expiry=utc_now() + timedelta(seconds=int(tok.get("expires_in", 3600))),
            scopes=tok.get("scope", "").split(),
        ), email  # ⚠ ver nota: exchange_code devuelve (creds, email) — el caller lo separa

    async def refresh(self, creds: Credentials) -> Credentials:
        import httpx

        if creds.refresh_token is None:
            raise ValueError("no refresh_token")  # → CALENDAR_TOKEN_REFRESH_FAILED + needs_reauth
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": creds.refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()      # invalid_grant → 400 → needs_reauth
            tok = resp.json()
        return Credentials(
            access_token=tok["access_token"],
            refresh_token=creds.refresh_token,  # Google no re-emite el refresh en cada refresh
            expiry=utc_now() + timedelta(seconds=int(tok.get("expires_in", 3600))),
            scopes=tok.get("scope", "").split() or creds.scopes,
        )

    async def list_calendars(self, creds: Credentials) -> list[ExternalCalendar]:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_API_BASE}/users/me/calendarList",
                headers={"Authorization": f"Bearer {creds.access_token}"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        return [
            ExternalCalendar(
                id=c["id"], name=c.get("summary", c["id"]), primary=bool(c.get("primary"))
            )
            for c in items
        ]

    async def list_events(
        self, creds: Credentials, *, calendar_id: str, time_min: datetime, time_max: datetime
    ) -> list[ExternalEvent]:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_API_BASE}/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                params={
                    "timeMin": time_min.isoformat(),
                    "timeMax": time_max.isoformat(),
                    "singleEvents": "true",   # expande recurrencias a instancias concretas
                    "orderBy": "startTime",
                    "maxResults": 250,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        return [_parse_google_event(e) for e in items if e.get("status") != "cancelled"]
```

> ⚠ **`exchange_code` devuelve `(Credentials, email)`** en Google (el `account_email` sale de `userinfo`, no del token). El Protocol declara `-> Credentials` por simplicidad del contrato común; en la práctica `oauth.handle_callback` consume la tupla. Alternativa más limpia: un método aparte `async get_account_email(creds) -> str` en el Protocol (Microsoft lo resuelve con `GET /me`). **Decidir en F1**; el doc deja el método aparte como la opción recomendada para no romper la firma `-> Credentials`. `_parse_google_event` mapea `start.dateTime`/`start.date` (all-day) → `ExternalEvent` con `_as_utc`.

### `services/providers/microsoft.py` — `MicrosoftGraphAdapter` (httpx async, Entra ID)

Mismo patrón con los endpoints de Microsoft Graph. Tenant = `Settings.MICROSOFT_OAUTH_TENANT` (default `common`). Scope `offline_access Calendars.Read`.

```python
_AUTH_BASE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_API_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = "offline_access Calendars.Read User.Read"
```

- `build_auth_url`: `response_type=code` + `scope=_SCOPE` + `state` (idéntico patrón).
- `exchange_code`: `POST {token}` con `grant_type=authorization_code`; el `account_email` sale de `GET /me` (`userPrincipalName`/`mail`).
- `refresh`: `POST {token}` con `grant_type=refresh_token` (Microsoft **sí** re-emite el `refresh_token` en cada refresh → guardar el nuevo).
- `list_calendars`: `GET /me/calendars` → `{id, name, isDefaultCalendar}` (el `primary` = `isDefaultCalendar`).
- `list_events`: `GET /me/calendars/{id}/calendarView?startDateTime&endDateTime`, header `Prefer: outlook.timezone="UTC"` (Graph devuelve los instantes en UTC). Mapear `start.dateTime`/`end.dateTime` + `isAllDay`.

> ⚠ **Outlook.com personal** (decisión LOCKED #6): `calendarView` (lectura de eventos) **funciona**; lo que NO soporta cuentas personales es `getSchedule` (el free/busy del **modo bloqueante futuro**). Documentar la limitación en `get_busy` (comentado en el Protocol), no en Fase 1/2.

### `services/providers/__init__.py` — factory (`get_adapter`)

```python
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

_CALENDAR_ADAPTERS: dict[CalendarProvider, Callable[[str], _CalendarAdapter]] = {
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
    return _CALENDAR_ADAPTERS[key]("")  # el arg str (model) se ignora; iguala la firma del molde
```

## Almacenamiento de tokens — extensión de `app.core.secrets` (ADR-010)

Hoy [`app.core.secrets`](../../../backend/app/core/secrets.py) es **read-only** (`resolve(name) -> dict` con cache TTL de 600s + cliente lazy). `calendar` necesita **escribir** (guardar tokens al conectar + rotar el access token al refrescar). **Agregar** una función `put` que crea el secreto si no existe + agrega una versión + invalida la cache:

```python
async def put(secret_name: str, payload: dict[str, Any]) -> None:
    """Crea el secreto (si no existe) + agrega una versión con `payload` (JSON). Idempotente
    en la creación (AlreadyExists se ignora). Invalida la cache del secreto para que el
    próximo resolve() lea la versión nueva. Reusa el resource path de resolve().

    La SA de Cloud Run ya tiene `secretmanager.secretAccessor`; ESTO requiere además
    `secretmanager.admin` (o secretVersionAdder + el create) a nivel proyecto/secreto.
    Error → CALENDAR_CREDENTIALS_MISSING (espeja CHANNEL_CREDENTIALS_MISSING de resolve)."""
    settings = get_settings()
    project = f"projects/{settings.GCP_PROJECT_ID}"
    parent = f"{project}/secrets/{secret_name}"
    data = json.dumps(payload).encode("utf-8")
    try:
        client = _get_client()
        try:
            await client.create_secret(
                parent=project,
                secret_id=secret_name,
                secret={"replication": {"automatic": {}}},
            )
        except Exception:  # AlreadyExists — el secreto ya existe, seguimos a add_version
            pass
        await client.add_secret_version(parent=parent, payload={"data": data})
    except Exception as exc:
        raise BadRequestException(
            "No se pudo escribir el secreto del calendario", code="CALENDAR_CREDENTIALS_MISSING"
        ) from exc
    _CACHE.pop(secret_name, None)  # invalida la cache (rotación inmediata)
```

> ⚠ **Misma cache `_CACHE` y mismo `_get_client()`** del resolver — `put` vive en el **mismo** `app/core/secrets.py` (no un archivo nuevo). El `secret_name` por conexión es `f"medisage-calendar-{connection_id}-{settings.ENV_NAME}"` (lo arma el service, no el secrets module). El payload es `{access_token, refresh_token, expiry (ISO), scopes}` (`Credentials` serializado). `resolve()` lo lee de vuelta y el service lo rehidrata a `Credentials` (parse `expiry` con `datetime.fromisoformat`, `_as_utc`).

> El **cliente OAuth** (client_id/secret por provider) **NO** va por conexión: es **global por entorno** (Settings + `--set-secrets`), modelo single-tenant de Cal.com (un cliente OAuth a nivel app + N tokens por-cuenta). Lo de Secret Manager por-conexión son **solo los tokens del usuario**.

## Settings (config.py) + boot-validator + deploy

Agregar a `app/core/config.py:Settings` (tras el bloque de `bots`):

```python
# ── Calendar (módulo #9, ADR-014) ──
# Cliente OAuth por proveedor (global por entorno; los *_SECRET vía --set-secrets de
# Cloud Run). Defaults vacíos → el módulo es INERTE (no se puede conectar) hasta
# configurar las credenciales. El smoke (ENV_NAME=dev) NO toca OAuth.
GOOGLE_OAUTH_CLIENT_ID: str = ""
GOOGLE_OAUTH_CLIENT_SECRET: str = ""        # Secret Manager
MICROSOFT_OAUTH_CLIENT_ID: str = ""
MICROSOFT_OAUTH_CLIENT_SECRET: str = ""     # Secret Manager
MICROSOFT_OAUTH_TENANT: str = "common"      # 'common' | 'organizations' | un tenant id
# Base pública para el redirect_uri del callback (= SERVICE_BASE_URL, sin trailing slash).
# El redirect_uri efectivo = f"{CALENDAR_OAUTH_REDIRECT_BASE}/api/v1/calendar/oauth/{provider}/callback".
CALENDAR_OAUTH_REDIRECT_BASE: str = ""
```

**Boot-validator** `_enforce_calendar_oauth` (espejo exacto de `_enforce_bot_dispatch_secret`):

```python
@model_validator(mode="after")
def _enforce_calendar_oauth(self) -> Settings:
    """Si un proveedor de calendario está PARCIALMENTE configurado (client_id seteado),
    fuera de `dev` DEBE traer su client_secret real (≥ algún mínimo) o NO arrancar. Falla
    RUIDOSA al boot en vez de un OAuth medio-configurado que solo falle en runtime (mismo
    principio que el resto de validadores: nada que solo falle en prod). Si el redirect
    base falta con cualquier provider configurado, también falla."""
    if self.ENV_NAME == "dev":
        return self
    providers = [
        ("GOOGLE", self.GOOGLE_OAUTH_CLIENT_ID, self.GOOGLE_OAUTH_CLIENT_SECRET),
        ("MICROSOFT", self.MICROSOFT_OAUTH_CLIENT_ID, self.MICROSOFT_OAUTH_CLIENT_SECRET),
    ]
    any_configured = False
    for name, client_id, client_secret in providers:
        if not client_id:
            continue
        any_configured = True
        if len(client_secret.strip()) < 8:
            raise ValueError(
                f"{name}_OAUTH_CLIENT_ID is set but {name}_OAUTH_CLIENT_SECRET is missing/too "
                f"short for ENV_NAME={self.ENV_NAME!r}. Set the per-environment secret."
            )
    if any_configured and not self.CALENDAR_OAUTH_REDIRECT_BASE.strip():
        raise ValueError(
            "A calendar OAuth provider is configured but CALENDAR_OAUTH_REDIRECT_BASE is empty. "
            "Set it to the public service base URL (no trailing slash)."
        )
    return self
```

- **Defaults vacíos → el módulo es INERTE** (no se puede conectar) hasta configurar credenciales. El smoke (ENV=dev) NO toca OAuth: ningún test arranca un flujo real.
- **Deploy (lección §9/§11)**: agregar las env-vars a `--set-env-vars` y los `*_SECRET` a `--set-secrets` de **AMBOS** workflows `deploy-backend-{qa,prod}.yml`. Secrets nuevos: `medisage-google-oauth-client-secret-{qa,prod}` + `medisage-microsoft-oauth-client-secret-{qa,prod}`. **Sumar el rol `secretmanager.admin`** (o `secretVersionAdder` + create) a la SA de Cloud Run (para `secrets.put`).
- **conftest**: si el validator nuevo tiene efecto al boot, los defaults vacíos lo dejan no-op en tests (ENV_NAME=dev). No hace falta tocar `conftest.py` salvo que un test setee `ENV_NAME != dev` con un provider a medias.

## Schemas Pydantic v2 — completos

> ⚠ **Convenciones aplicadas** (idénticas a [`../scheduling/backend.md`](../scheduling/backend.md#schemas-pydantic-v2--completos)): no usar Ellipsis (`...`) en `Field(...)`; `Annotated` solo para `Query`/`Path` en routers; validators con mensajes en inglés; `model_config = ConfigDict(from_attributes=True)` en los schemas de salida.

### `schemas/connection.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.calendar.enums import CalendarProvider, ConnectionStatus
from app.modules.calendar.schemas.source import CalendarSourceItem


class CalendarConnectionItem(BaseModel):
    """Fila de la lista de conexiones. `is_active` = ActiveMixin.active (pausa manual);
    sources_count = denorm (batch count). NINGÚN denorm en ALLOWED_FIELDS (cd10c78)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: CalendarProvider
    account_email: str
    display_name: str | None
    status: ConnectionStatus
    scopes: str | None = None
    last_checked_at: datetime | None = None
    sources_count: int = 0
    is_active: bool  # mapea active
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class CalendarConnectionDetail(CalendarConnectionItem):
    """Detalle: agrega los sources mapeados + el último error (observabilidad)."""

    sources: list[CalendarSourceItem]
    last_error: str | None = None


class OAuthStartResponse(BaseModel):
    """Respuesta de GET /oauth/{provider}/start — el front redirige a auth_url."""

    auth_url: str


class CalendarProviderOption(BaseModel):
    """Para la UI 'Conectar X' (botones header). value = CalendarProvider, label español."""

    value: CalendarProvider
    label: str
```

> `CalendarConnectionDetail` referencia `CalendarSourceItem` de `schemas/source.py` (import directo, sin ciclo: `source.py` no importa `connection.py`). `is_active` mapea `active` por alias del service (al armar el Item desde el modelo, `is_active=conn.active`); el `from_attributes` no auto-renombra `active→is_active`, así que el service lo arma explícito (o se usa un `@computed_field`/alias — preferir armado explícito en el service, patrón shipped).

### `schemas/source.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CalendarSourceItem(BaseModel):
    """Una fila de mapeo calendario→sede. branch_name denorm (NULL = 'Todas las sedes').
    is_enabled = ActiveMixin.active (flag de lectura, NO 2ª columna)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    connection_id: str
    external_calendar_id: str
    external_calendar_name: str
    branch_id: str | None = None
    branch_name: str | None = None  # denorm de clinic.Branch.name (None si branch_id NULL)
    is_enabled: bool  # mapea active


class CalendarSourceCreate(BaseModel):
    """Un mapeo en el body del bulk-replace. branch_id None = 'todas las sedes'."""

    external_calendar_id: str = Field(min_length=1, max_length=255)
    external_calendar_name: str = Field(min_length=1, max_length=255)
    branch_id: str | None = None
    is_enabled: bool = True


class CalendarSourcesReplace(BaseModel):
    """Body de PUT /connections/{id}/sources — REEMPLAZA el set completo de sources
    (patrón clinic.OfficeOperatingHours bulk-replace). min 0 (vaciar el mapeo es válido)."""

    sources: list[CalendarSourceCreate] = Field(default_factory=list)


class ExternalCalendarOption(BaseModel):
    """De list_calendars (live) — el dropdown de mapeo. NO se persiste (es del provider)."""

    id: str
    name: str
    primary: bool = False
```

### `schemas/external_event.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.calendar.enums import ConnectionStatus


class ExternalEventItem(BaseModel):
    """Un evento externo para el overlay. starts_at/ends_at UTC (el front los ubica en hora
    local del navegador, igual que las citas). branch_id/branch_name resuelven la sede del source (None = global).
    source_id ata el evento a su CalendarSource (para la leyenda/atenuado de la grilla)."""

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    branch_id: str | None = None
    branch_name: str | None = None
    source_id: str


class SourceHealth(BaseModel):
    """Salud de una conexión tras el intento de lectura (best-effort). error = code (None=OK)."""

    connection_id: str
    status: ConnectionStatus
    error: str | None = None


class ExternalEventsResponse(BaseModel):
    """Respuesta de GET /external-events. events = lo leído (de las conexiones que
    respondieron); sources_health = el estado por conexión (las que fallaron NO rompen
    la respuesta — la grilla muestra un aviso suave de salud)."""

    events: list[ExternalEventItem] = Field(default_factory=list)
    sources_health: list[SourceHealth] = Field(default_factory=list)
```

## Repositories

`ALLOWED_FIELDS` = whitelist de columnas filtrable/ordenable desde el frontend. **Solo columnas reales** de la tabla (lección `cd10c78`): `sources_count`/`branch_name`/`account_email`-display NO son denorm pero `sources_count` SÍ es derivado → NO va en `ALLOWED_FIELDS`.

### `repositories/calendar_connection.py`

```python
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.calendar.models.calendar_connection import CalendarConnection
from app.modules.calendar.models.calendar_source import CalendarSource
from app.shared.base_repository import BaseRepository


class CalendarConnectionRepository(BaseRepository[CalendarConnection]):
    # Solo columnas reales. provider/account_email/status/active son filtrables; los denorm
    # (sources_count) NO.
    ALLOWED_FIELDS: set[str] = {
        "provider", "account_email", "status", "active", "created_on", "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(CalendarConnection)

    async def get_by_provider_email(
        self, db: AsyncSession, provider: str, account_email: str
    ) -> CalendarConnection | None:
        """Guard de UNIQUE PARCIAL (CALENDAR_CONNECTION_ALREADY_EXISTS). Solo vivas."""
        result = await db.execute(
            select(CalendarConnection).where(
                CalendarConnection.provider == provider,
                CalendarConnection.account_email == account_email,
                CalendarConnection.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, connection_id: str) -> CalendarConnection | None:
        """Detalle: carga los sources VIVOS con selectinload (la relación es lazy='raise')."""
        result = await db.execute(
            select(CalendarConnection)
            .where(
                CalendarConnection.id == connection_id,
                CalendarConnection.deleted_at.is_(None),
            )
            .options(selectinload(CalendarConnection.sources))
        )
        conn = result.scalars().first()
        if conn is not None:
            conn.sources = [s for s in conn.sources if s.deleted_at is None]  # filtra SD en memoria
        return conn

    async def sources_count_map(
        self, db: AsyncSession, connection_ids: list[str]
    ) -> dict[str, int]:
        """Batch (sin N+1) para denormalizar sources_count en la lista de conexiones."""
        if not connection_ids:
            return {}
        result = await db.execute(
            select(CalendarSource.connection_id, func.count())
            .where(
                CalendarSource.connection_id.in_(connection_ids),
                CalendarSource.deleted_at.is_(None),
            )
            .group_by(CalendarSource.connection_id)
        )
        return {row[0]: row[1] for row in result.all()}
```

### `repositories/calendar_source.py`

```python
class CalendarSourceRepository(BaseRepository[CalendarSource]):
    ALLOWED_FIELDS: set[str] = set()  # no hay /list de sources; se leen por connection/branch

    def __init__(self) -> None:
        super().__init__(CalendarSource)

    async def list_for_connection(
        self, db: AsyncSession, connection_id: str
    ) -> list[CalendarSource]:
        result = await db.execute(
            select(CalendarSource).where(
                CalendarSource.connection_id == connection_id,
                CalendarSource.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_enabled_for_branch(
        self, db: AsyncSession, branch_id: str
    ) -> list[CalendarSource]:
        """Sources HABILITADOS (active=true) de la sede: branch_id == X OR branch_id IS NULL
        ('todas las sedes'). Es el conjunto que GET /external-events resuelve por sede."""
        result = await db.execute(
            select(CalendarSource).where(
                CalendarSource.active.is_(True),
                CalendarSource.deleted_at.is_(None),
                (CalendarSource.branch_id == branch_id)
                | (CalendarSource.branch_id.is_(None)),
            )
        )
        return list(result.scalars().all())

    async def soft_delete_for_connection(self, db: AsyncSession, connection_id: str) -> None:
        """Bulk-replace paso 1: soft-deletea los sources vivos de la conexión (el caller
        inserta el set nuevo con audit cols). NO usa DELETE real (mantiene la traza + libera
        el UNIQUE PARCIAL). Patrón clinic.OfficeOperatingHours.replace."""
        # UPDATE calendar_source SET deleted_at=now() WHERE connection_id=:c AND deleted_at IS NULL
        ...
```

> ⚠ El bulk-replace **soft-deletea** (no DELETE real) los sources viejos: la `cascade="all, delete-orphan"` del relationship es solo para el hard-delete del modelo; el replace de negocio usa `soft_delete_for_connection` + insert. El UNIQUE PARCIAL `(connection_id, external_calendar_id) WHERE deleted_at IS NULL` deja re-mapear el mismo calendario tras el soft-delete (igual que `crm.person_lead_status` reabre).

## Services

### `services/oauth.py` — start (state firmado) + callback (exchange + secrets.put + crea conexión)

El `state` es un **JWT firmado con `SECRET_KEY`** (mismo `jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)` de `app.core.security`), con `actor_id` + nonce + provider + return_to + exp corto (CSRF + anti-replay). El callback es **PÚBLICO** (sin RBAC) y se gatea por la firma del state.

```python
"""
Flujo OAuth de calendar (molde: el webhook PÚBLICO de conversations + el JWT de
app.core.security). start firma un `state` (JWT, exp corto); callback valida el state →
exchange_code → secrets.put(tokens) → crea CalendarConnection → 302 al return_to del front.
NUNCA expone el client_secret ni el token al browser (todo server-side, como el template).
"""

from __future__ import annotations

import jwt

from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.core.security import ALGORITHM
from app.core import secrets
from app.modules.calendar.enums import CalendarProvider, ConnectionStatus
from app.modules.calendar.repositories.calendar_connection import (
    calendar_connection_repository,
)
from app.modules.calendar.schemas.connection import OAuthStartResponse
from app.modules.calendar.services.providers import get_adapter
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now

_STATE_TTL_SECONDS = 600  # 10 min: el consentimiento OAuth es corto


def _redirect_uri(provider: str) -> str:
    settings = get_settings()
    base = settings.CALENDAR_OAUTH_REDIRECT_BASE.rstrip("/")
    return f"{base}/api/v1/calendar/oauth/{provider}/callback"


async def build_start_url(
    provider: str, *, actor_id: str, return_to: str
) -> SingleResponse[OAuthStartResponse]:
    adapter = get_adapter(provider)  # valida el provider (CALENDAR_PROVIDER_NOT_SUPPORTED)
    settings = get_settings()
    now = utc_now()
    state = jwt.encode(
        {
            "actor_id": actor_id,
            "provider": provider,
            "return_to": return_to,
            "nonce": generate_uuid(),
            "iat": now,
            "exp": now.timestamp() + _STATE_TTL_SECONDS,
            "purpose": "calendar_oauth",
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    auth_url = adapter.build_auth_url(state=state, redirect_uri=_redirect_uri(provider))
    return SingleResponse(data=OAuthStartResponse(auth_url=auth_url))


def _decode_state(state: str, provider: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise BadRequestException("State inválido o expirado", code="CALENDAR_OAUTH_STATE_INVALID") from exc
    if payload.get("purpose") != "calendar_oauth" or payload.get("provider") != provider:
        raise BadRequestException("State inválido", code="CALENDAR_OAUTH_STATE_INVALID")
    return payload


async def handle_callback(db, provider: str, *, code: str, state: str) -> str:
    """Valida state → exchange → secrets.put → crea/actualiza CalendarConnection. Devuelve el
    return_to (el ROUTER hace el 302). Errores de dominio → el router los traduce a un 302
    con ?calendar_error=CODE (no rompe la ventana del usuario)."""
    payload = _decode_state(state, provider)  # CALENDAR_OAUTH_STATE_INVALID
    adapter = get_adapter(provider)
    try:
        creds, account_email = await adapter.exchange_code(
            code=code, redirect_uri=_redirect_uri(provider)
        )  # ver nota base.py: exchange_code → (Credentials, email)
    except Exception as exc:
        raise BadRequestException(
            "No se pudo completar el OAuth", code="CALENDAR_OAUTH_EXCHANGE_FAILED"
        ) from exc

    existing = await calendar_connection_repository.get_by_provider_email(
        db, provider, account_email
    )
    if existing is not None:
        # reconexión: refresca el secreto + status=connected (no crea fila nueva).
        await secrets.put(existing.secret_name, _creds_payload(creds))
        existing.status = ConnectionStatus.connected.value
        existing.scopes = " ".join(creds.scopes)
        existing.last_checked_at = utc_now()
        existing.last_error = None
        existing.updated_by = payload["actor_id"]; existing.updated_on = utc_now()
        await db.flush()
        return payload["return_to"]

    settings = get_settings()
    conn_id = generate_uuid()
    secret_name = f"medisage-calendar-{conn_id}-{settings.ENV_NAME}"
    await secrets.put(secret_name, _creds_payload(creds))   # tokens → Secret Manager
    now = utc_now()
    conn = CalendarConnection(
        id=conn_id, provider=provider, account_email=account_email,
        display_name=account_email, secret_name=secret_name,
        status=ConnectionStatus.connected.value, scopes=" ".join(creds.scopes),
        last_checked_at=now, active=True,
        created_by=payload["actor_id"], created_on=now,
        updated_by=payload["actor_id"], updated_on=now,
    )
    db.add(conn); await db.flush()
    return payload["return_to"]
```

> `_creds_payload(creds)` serializa `Credentials` a `{access_token, refresh_token, expiry: creds.expiry.isoformat(), scopes}`. El `get_by_provider_email` cubre el `CALENDAR_CONNECTION_ALREADY_EXISTS` (409) en el path de la **lista** (conectar 2 veces la misma cuenta viva desde un botón duplicado); en el **callback** la misma cuenta = reconexión (refresca el secreto, no 409). El secreto se nombra con el `connection_id` ⇒ se genera **antes** del `db.add` (lo necesita la fila).

### `services/connection.py` — list / get / disconnect / list_external_calendars

```python
async def list_connections(db, query) -> PaginatedResponse[CalendarConnectionItem]:
    items, total = await calendar_connection_repository.get_paginated(db, query)
    counts = await calendar_connection_repository.sources_count_map(db, [c.id for c in items])
    audit = await user_repository.get_audit_info_map(db, _audit_ids(items))
    return PaginatedResponse(data=PaginatedData(
        items=[_to_item(c, counts.get(c.id, 0), audit) for c in items],
        total=total, skip=query.pagination.skip, limit=query.pagination.limit))


async def get_connection(db, connection_id) -> SingleResponse[CalendarConnectionDetail]:
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")
    branch_names = await branch_repository.name_map(db, [s.branch_id for s in conn.sources if s.branch_id])
    return SingleResponse(data=_to_detail(conn, branch_names, audit))


async def disconnect(db, connection_id, *, actor_id) -> None:
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")
    # 1) best-effort revoke en el provider (NO rompe si falla) + 2) borra el secreto.
    await _best_effort_revoke_and_delete_secret(conn)
    # 3) soft-delete los sources + la conexión.
    await calendar_source_repository.soft_delete_for_connection(db, connection_id)
    await calendar_connection_repository.soft_delete(db, conn, actor_id=actor_id)
    await db.flush()


async def list_external_calendars(db, connection_id) -> SingleResponse[list[ExternalCalendarOption]]:
    """Live list_calendars (para la UI de mapeo). Refresca el token si expiró. Si el provider
    falla → CALENDAR_TOKEN_REFRESH_FAILED (la UI de config SÍ propaga el error, a diferencia
    del overlay que es best-effort)."""
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")
    adapter = get_adapter(conn.provider)
    creds = await _resolve_creds(db, conn, adapter)   # refresh al vuelo (ver external_read)
    calendars = await adapter.list_calendars(creds)
    return SingleResponse(data=[
        ExternalCalendarOption(id=c.id, name=c.name, primary=c.primary) for c in calendars
    ])
```

> El `disconnect` borra el secreto best-effort (un secreto huérfano no es crítico; un secreto borrado de una cuenta aún conectada sí, así que el revoke va primero). El `list_external_calendars` es de **config** (CALENDAR_CONNECTIONS_WRITE) → SÍ propaga el error del provider (la UI de mapeo necesita saber que falló); el **overlay** (`external_read`) NO (best-effort).

### `services/source.py` — replace_sources (bulk REPLACE atómico, valida branch_id)

```python
async def replace_sources(
    db, connection_id, payload: CalendarSourcesReplace, *, actor_id
) -> SingleResponse[CalendarConnectionDetail]:
    """Bulk REPLACE atómico (patrón clinic.OfficeOperatingHours): soft-delete los viejos +
    insert el set nuevo, en la MISMA tx del request. Valida cada branch_id ANTES de insertar
    (404 BRANCH_NOT_FOUND, lección §20/§22 — todo FK real que el payload traiga se valida)."""
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")

    # 1) Validar branch_ids (los no-NULL) contra clinic.branch VIVO.
    branch_ids = [s.branch_id for s in payload.sources if s.branch_id is not None]
    if branch_ids:
        existing = await branch_repository.get_by_ids(db, list(set(branch_ids)))
        existing_ids = {b.id for b in existing}
        for bid in branch_ids:
            if bid not in existing_ids:
                raise NotFoundException(f"Sede {bid} no encontrada", code="BRANCH_NOT_FOUND")

    # 2) Soft-delete los sources viejos + insert el set nuevo (misma tx → atómico).
    await calendar_source_repository.soft_delete_for_connection(db, connection_id)
    now = utc_now()
    for s in payload.sources:
        db.add(CalendarSource(
            id=generate_uuid(), connection_id=connection_id,
            external_calendar_id=s.external_calendar_id,
            external_calendar_name=s.external_calendar_name,
            branch_id=s.branch_id, active=s.is_enabled,   # is_enabled → ActiveMixin.active
            created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now))
    await db.flush()
    return await get_connection(db, connection_id)  # reload-via-get (relación lazy='raise')
```

> ⚠ **Validar el FK ANTES del insert** (lección §20/§22): un `branch_id` inexistente debe dar **404 `BRANCH_NOT_FOUND`**, no un 500 por el FK constraint. Se valida en bloque (un `get_by_ids` batch, no N+1). El replace es atómico por la tx del request (`get_db` commitea al final): si el insert lanza (p.ej. un duplicado de `external_calendar_id` en el payload), rollback y el mapeo viejo queda intacto.

### `services/external_read.py` — read_external_events (best-effort, NUNCA 5xx)

El corazón de F2. **Best-effort, aislado** (lección §23): si una conexión falla (token revocado, provider caído, rate limit), marca su salud y sigue; **NUNCA un 5xx, nunca rompe la grilla**.

```python
"""
Lectura informativa on-demand (Fase 2). Resuelve los CalendarSource habilitados de la
sede (branch_id == X OR NULL), agrupa por conexión, refresca el token si expiró, llama
list_events por calendario y aplana a ExternalEventItem. AISLAMIENTO (regla §23): cada
conexión se intenta dentro de un try; un fallo marca sources_health y NO contamina el
resto. NUNCA propaga un 5xx (a diferencia de list_external_calendars, que es de config).
"""

from __future__ import annotations

from datetime import datetime

from app.modules.calendar.enums import ConnectionStatus
from app.modules.calendar.schemas.external_event import (
    ExternalEventItem, ExternalEventsResponse, SourceHealth,
)
from app.modules.calendar.services.providers import get_adapter
from app.modules.calendar.services.providers.base import Credentials
from app.core import secrets
from app.shared.base_schemas import SingleResponse
from app.shared.utils import utc_now


async def _resolve_creds(db, conn, adapter) -> Credentials:
    """Lee el secreto → Credentials; si expiry < now (con margen) refresca y RE-ESCRIBE el
    secreto (secrets.put). invalid_grant → marca la conexión needs_reauth + CALENDAR_TOKEN_REFRESH_FAILED."""
    raw = await secrets.resolve(conn.secret_name)   # ADR-010 (CALENDAR_CREDENTIALS_MISSING si falla)
    creds = _creds_from_payload(raw)
    if creds.expiry <= utc_now():
        try:
            creds = await adapter.refresh(creds)
        except Exception as exc:
            conn.status = ConnectionStatus.needs_reauth.value
            conn.last_error = "invalid_grant"
            raise BadRequestException(
                "No se pudo refrescar el token", code="CALENDAR_TOKEN_REFRESH_FAILED"
            ) from exc
        await secrets.put(conn.secret_name, _creds_payload(creds))  # rota el access token
    return creds


async def read_external_events(
    db, *, branch_id: str, time_min: datetime, time_max: datetime
) -> SingleResponse[ExternalEventsResponse]:
    sources = await calendar_source_repository.list_enabled_for_branch(db, branch_id)
    # branch_name denorm (None si branch_id NULL = 'todas las sedes').
    branch_names = await branch_repository.name_map(db, [s.branch_id for s in sources if s.branch_id])
    # agrupar sources por conexión (un refresh por conexión, no por calendario).
    by_connection: dict[str, list] = _group_by_connection(sources)

    events: list[ExternalEventItem] = []
    health: list[SourceHealth] = []
    for connection_id, conn_sources in by_connection.items():
        conn = await calendar_connection_repository.get_by_id(db, connection_id)
        if conn is None or not conn.active:
            continue
        adapter = get_adapter(conn.provider)
        try:
            creds = await _resolve_creds(db, conn, adapter)
            for src in conn_sources:
                ext = await adapter.list_events(
                    creds, calendar_id=src.external_calendar_id,
                    time_min=time_min, time_max=time_max)
                events.extend(
                    ExternalEventItem(
                        external_id=e.external_id, title=e.title,
                        starts_at=e.starts_at, ends_at=e.ends_at, all_day=e.all_day,
                        branch_id=src.branch_id,
                        branch_name=branch_names.get(src.branch_id) if src.branch_id else None,
                        source_id=src.id,
                    ) for e in ext
                )
            conn.last_checked_at = utc_now(); conn.last_error = None
            health.append(SourceHealth(connection_id=conn.id, status=ConnectionStatus(conn.status)))
        except Exception as exc:  # noqa: BLE001 — AISLAMIENTO §23: marcar salud y SEGUIR
            conn.last_error = str(exc)[:500]
            code = getattr(exc, "code", "CALENDAR_READ_FAILED")
            health.append(SourceHealth(
                connection_id=conn.id, status=ConnectionStatus(conn.status), error=code))
    return SingleResponse(data=ExternalEventsResponse(events=events, sources_health=health))
```

> ⚠ **Aislamiento por conexión** (lección §23, el contrato no-negociable): el `try/except` envuelve **toda** la lectura de una conexión; un provider caído marca `sources_health[].error` y el loop sigue con las demás. El endpoint **siempre** devuelve 200 con lo que pudo leer + la salud. La grilla del front renderiza las citas medisage normalmente + un aviso suave de salud. Esto es lo que hace que **un calendario externo caído no pueda romper la grilla ni la reserva** — la capa es puramente aditiva. (El `_resolve_creds` SÍ levanta dentro del try, pero queda atrapado por el except de la conexión → no escapa.)

### El `busy` hook FUTURO (modo bloqueante, B1 — documentado, NO implementado)

La Fase 1/2 **NO toca** [`scheduling/services/availability.py`](../../../backend/app/modules/scheduling/services/availability.py). El gancho del **modo bloqueante diferido (B1)** sería en `compute_available_slots`, donde hoy se arma `busy` (línea ~240):

```python
# availability.py:compute_available_slots (HOY — NO se modifica en Fase 1/2)
busy = [
    (_as_utc(a.scheduled_for), _as_utc(a.scheduled_for) + timedelta(minutes=a.duration_min))
    for a in appts
]
# ── B1 FUTURO (NO Fase 1): unir el busy externo como un MINUS extra (extiende ADR-006) ──
# external_busy = await calendar.external_read.get_busy_for(db, branch_id=branch_id,
#                                                           time_min=range_start, time_max=range_end)
# busy = busy + external_busy          # el resto del algoritmo (_subtract) ya lo absorbe
```

> Por qué encaja sin reescritura: `busy` es solo una lista de `(start, end)` UTC que `_subtract(windows, busy)` resta de las ventanas libres. El modo bloqueante = agregar los intervalos externos a esa lista. **Pero eso ACOPLA la correctitud del agendamiento a un sistema externo** (decisión LOCKED: Fase 1 informativa, no bloqueante) → B1 va detrás de `get_busy(...)` (free/busy opaco, no el detalle) y de un flag de configuración, en su propia fase. La Fase 1/2 deja `availability.py` intacto.

## Routers — ejemplos

Patrón shipped: permiso vía `dependencies=[Depends(RequirePermission("CODE"))]`; `actor: CurrentAuth` aparte cuando se necesita el id; las rutas estáticas antes de `/{id}`. El **callback es PÚBLICO** (sin RBAC, gateado por `state`) y responde **302** (no JSON) — molde del webhook público de conversations.

```python
# routers/oauth.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import RedirectResponse

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.calendar.schemas.connection import OAuthStartResponse
from app.modules.calendar.services import oauth as oauth_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/oauth", tags=["calendar · oauth"])

ProviderPath = Annotated[str, Path(min_length=1, description="google | microsoft")]


@router.get("/{provider}/start", response_model=SingleResponse[OAuthStartResponse],
            dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))])
async def oauth_start(
    provider: ProviderPath, db: DBSession, actor: CurrentAuth,
    return_to: Annotated[str, Query(description="URL del front a la que volver")],
) -> SingleResponse[OAuthStartResponse]:
    return await oauth_service.build_start_url(provider, actor_id=actor.id, return_to=return_to)


@router.get("/{provider}/callback", include_in_schema=False)  # PÚBLICO: sin RequirePermission
async def oauth_callback(
    provider: ProviderPath, db: DBSession,
    code: Annotated[str, Query()], state: Annotated[str, Query()],
) -> RedirectResponse:
    """Gateado por `state` (JWT firmado), NO por RBAC (la ventana OAuth no trae cookie de
    sesión del backend). Éxito → 302 al return_to; error de dominio → 302 con ?calendar_error=CODE
    (no rompe la ventana del usuario; el front muestra el error). NUNCA 5xx."""
    try:
        return_to = await oauth_service.handle_callback(db, provider, code=code, state=state)
        return RedirectResponse(url=return_to, status_code=302)
    except (BadRequestException, NotFoundException) as exc:
        code_ = getattr(exc, "code", "CALENDAR_OAUTH_EXCHANGE_FAILED")
        # El return_to NO es confiable si el state no decodificó → fallback a una ruta fija del front.
        fallback = _safe_return_to_from_state(state) or "/clinic/calendarios-externos"
        sep = "&" if "?" in fallback else "?"
        return RedirectResponse(url=f"{fallback}{sep}calendar_error={code_}", status_code=302)
```

```python
# routers/connection.py (extracto)
router = APIRouter(prefix="/connections", tags=["calendar · connections"])

ConnIdPath = Annotated[str, Path(min_length=1, description="Connection UUID")]


@router.post("/list", response_model=PaginatedResponse[CalendarConnectionItem],
             dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_READ"))])
async def list_connections(query: QueryRequest, db: DBSession) -> PaginatedResponse[CalendarConnectionItem]:
    return await connection_service.list_connections(db, query)


@router.get("/{connection_id}", response_model=SingleResponse[CalendarConnectionDetail],
            dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_READ"))])
async def get_connection(connection_id: ConnIdPath, db: DBSession) -> SingleResponse[CalendarConnectionDetail]:
    return await connection_service.get_connection(db, connection_id)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))])
async def disconnect(connection_id: ConnIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await connection_service.disconnect(db, connection_id, actor_id=actor.id)


@router.get("/{connection_id}/calendars", response_model=SingleResponse[list[ExternalCalendarOption]],
            dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))])
async def list_external_calendars(connection_id: ConnIdPath, db: DBSession) -> SingleResponse[list[ExternalCalendarOption]]:
    return await connection_service.list_external_calendars(db, connection_id)
```

```python
# routers/source.py
@router.put("/connections/{connection_id}/sources",
            response_model=SingleResponse[CalendarConnectionDetail],
            dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))])
async def replace_sources(
    connection_id: ConnIdPath, payload: CalendarSourcesReplace, db: DBSession, actor: CurrentAuth,
) -> SingleResponse[CalendarConnectionDetail]:
    return await source_service.replace_sources(db, connection_id, payload, actor_id=actor.id)


# routers/external_event.py
@router.get("/external-events", response_model=SingleResponse[ExternalEventsResponse],
            dependencies=[Depends(RequirePermission("CALENDAR_EXTERNAL_EVENTS_READ"))])
async def external_events(
    db: DBSession,
    branch_id: Annotated[str, Query()],
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
) -> SingleResponse[ExternalEventsResponse]:
    return await external_read.read_external_events(db, branch_id=branch_id, time_min=from_, time_max=to)
```

> ⚠ `from` es palabra reservada en Python → el query param se declara `from_` con `Query(alias="from")` (la URL usa `?from=`). El callback usa `include_in_schema=False` (no ensucia el Swagger con un endpoint de máquina) y responde **302** — un router que devuelve `RedirectResponse`/204 es la excepción a "los services devuelven el envelope" (el redirect es transporte, no payload de dominio).

## API contracts

Envelopes del template (idénticos a [`../scheduling/backend.md`](../scheduling/backend.md#api-contracts)): `SingleResponse` `{success, data}`, `PaginatedResponse` `{success, data:{items,total,skip,limit}}`, lista cruda en `/calendars`, error `{success, detail, code?, errors?}`. Prefijo común `/api/v1/calendar/`. Listados con `POST /<recurso>/list` + `QueryRequest`. `PUT` (no `PATCH`); rutas estáticas antes de `/{id}`.

### OAuth

#### `GET /api/v1/calendar/oauth/{provider}/start?return_to=` — `CALENDAR_CONNECTIONS_WRITE` → `SingleResponse[OAuthStartResponse]`
```json
{ "success": true, "data": { "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&state=eyJ..." } }
```
**Error 400** (`provider` desconocido): `{ "success": false, "detail": "Proveedor de calendario no soportado: 'apple'", "code": "CALENDAR_PROVIDER_NOT_SUPPORTED" }`

#### `GET /api/v1/calendar/oauth/{provider}/callback?code&state` — **PÚBLICO** → `302`
- Éxito → `302 Location: {return_to}`.
- `state` inválido/expirado → `302 Location: {fallback}?calendar_error=CALENDAR_OAUTH_STATE_INVALID`.
- exchange falló → `...?calendar_error=CALENDAR_OAUTH_EXCHANGE_FAILED`.

### Connections

#### `POST /api/v1/calendar/connections/list` — `CALENDAR_CONNECTIONS_READ` → `PaginatedResponse[CalendarConnectionItem]`
```json
{ "success": true, "data": { "items": [
  { "id": "cc1...", "provider": "google", "account_email": "clinica@gmail.com",
    "display_name": "clinica@gmail.com", "status": "connected", "scopes": "calendar.readonly",
    "last_checked_at": "2026-06-22T15:00:00+00:00", "sources_count": 2, "is_active": true,
    "created_on": "...", "created_by": "u1...", "updated_on": "...", "updated_by": "u1..." }
], "total": 1, "skip": 0, "limit": 10 } }
```

#### `GET /api/v1/calendar/connections/{id}` — `CALENDAR_CONNECTIONS_READ` → `SingleResponse[CalendarConnectionDetail]`
Incluye `sources` (con `branch_name` denorm) + `last_error`. **404** → `CALENDAR_CONNECTION_NOT_FOUND`.

#### `DELETE /api/v1/calendar/connections/{id}` — `CALENDAR_CONNECTIONS_WRITE` → `204`
Soft-delete + best-effort revoke en el provider + borra el secreto. **404** → `CALENDAR_CONNECTION_NOT_FOUND`.

#### `GET /api/v1/calendar/connections/{id}/calendars` — `CALENDAR_CONNECTIONS_WRITE` → `SingleResponse[list[ExternalCalendarOption]]`
Live `list_calendars` (refresca el token si expiró). **400** → `CALENDAR_TOKEN_REFRESH_FAILED` (la UI de config SÍ ve el error). Lista cruda dentro del `data`:
```json
{ "success": true, "data": [
  { "id": "primary", "name": "Sede Miraflores", "primary": true },
  { "id": "abc@group.calendar.google.com", "name": "Sede San Isidro", "primary": false }
] }
```

### Sources

#### `PUT /api/v1/calendar/connections/{id}/sources` — `CALENDAR_CONNECTIONS_WRITE` → `SingleResponse[CalendarConnectionDetail]`
**Request** (`CalendarSourcesReplace`) — REEMPLAZA el set completo:
```json
{ "sources": [
  { "external_calendar_id": "primary", "external_calendar_name": "Sede Miraflores", "branch_id": "b1...", "is_enabled": true },
  { "external_calendar_id": "abc@group.calendar.google.com", "external_calendar_name": "Personal", "branch_id": null, "is_enabled": false }
] }
```
**Error 404** (sede inexistente): `{ "success": false, "detail": "Sede b9... no encontrada", "code": "BRANCH_NOT_FOUND" }`
**Error 404** (conexión): `CALENDAR_CONNECTION_NOT_FOUND`.

### External events

#### `GET /api/v1/calendar/external-events?branch_id=&from=&to=` — `CALENDAR_EXTERNAL_EVENTS_READ` → `SingleResponse[ExternalEventsResponse]`
**best-effort, SIEMPRE 200** (nunca 5xx). Una conexión que falla aparece en `sources_health` con su `error`:
```json
{ "success": true, "data": {
  "events": [
    { "external_id": "ev_abc", "title": "Reunión proveedores", "starts_at": "2026-06-22T14:00:00+00:00",
      "ends_at": "2026-06-22T15:00:00+00:00", "all_day": false, "branch_id": "b1...",
      "branch_name": "Sede Miraflores", "source_id": "cs1..." }
  ],
  "sources_health": [
    { "connection_id": "cc1...", "status": "connected", "error": null },
    { "connection_id": "cc2...", "status": "needs_reauth", "error": "CALENDAR_TOKEN_REFRESH_FAILED" }
  ]
} }
```

## Códigos de error (en service, `detail` español + `code` inglés)

| Code | HTTP | Cuándo |
|---|---|---|
| `CALENDAR_CONNECTION_NOT_FOUND` | 404 | conexión inexistente / borrada |
| `CALENDAR_SOURCE_NOT_FOUND` | 404 | source inexistente (no usado en F1 — el replace no lee por id, reservado) |
| `CALENDAR_PROVIDER_NOT_SUPPORTED` | 400 | provider fuera de `_CALENDAR_ADAPTERS` (`get_adapter`) |
| `CALENDAR_OAUTH_STATE_INVALID` | 400 | `state` CSRF inválido/expirado en el callback |
| `CALENDAR_OAUTH_EXCHANGE_FAILED` | 400 | `exchange_code` falló en el proveedor |
| `CALENDAR_CONNECTION_ALREADY_EXISTS` | 409 | misma `(provider, account_email)` viva (botón de conectar duplicado) |
| `CALENDAR_TOKEN_REFRESH_FAILED` | 400 | refresh falló (`invalid_grant`) → conexión `needs_reauth` |
| `CALENDAR_CREDENTIALS_MISSING` | 400 | secreto no resoluble (espeja `CHANNEL_CREDENTIALS_MISSING` de ADR-010) |
| `BRANCH_NOT_FOUND` | 404 | mapear un source a una sede inexistente (valida FK antes de insertar, §20/§22) |

> En `read_external_events` los codes **NO se lanzan** (se capturan): `CALENDAR_TOKEN_REFRESH_FAILED`/`CALENDAR_CREDENTIALS_MISSING`/`CALENDAR_READ_FAILED` viajan dentro de `sources_health[].error` (string), no como un 4xx/5xx — la lectura es best-effort. En `list_external_calendars` (config) SÍ se lanzan (la UI de mapeo necesita el 400).

## Permisos (4) + subsets de rol

En `_seed-and-roles.md` + `seed.py:SEED_PERMISSIONS` (F0, forward-declarados; `_seed_role` filtra los inexistentes — se autoactivan, patrón scheduling F0):

- `MENU-CALENDAR` — muestra el child de nav.
- `CALENDAR_CONNECTIONS_READ` — ver conexiones + sources + salud.
- `CALENDAR_CONNECTIONS_WRITE` — conectar/desconectar + mapear (cubre OAuth start, `/calendars`, sources PUT, DELETE).
- `CALENDAR_EXTERNAL_EVENTS_READ` — leer el overlay (`GET /external-events`).

Subsets: **ADMIN** = los 4. **ASESOR** = `MENU-CALENDAR` + `CALENDAR_CONNECTIONS_READ` + `CALENDAR_EXTERNAL_EVENTS_READ` (config read-only + overlay). **DOCTOR** = `CALENDAR_EXTERNAL_EVENTS_READ` (solo el overlay en la grilla/su agenda; sin menú de config).

> El callback OAuth NO lleva permiso (es público, gateado por `state`); el resto del flujo de escritura va bajo `CALENDAR_CONNECTIONS_WRITE` (el actor que inició el `start` queda en el `state` y termina como `created_by` de la conexión).

## Migration draft — `0025_calendar_connection` (F1)

`down_revision = "0024_marketing_promotion_usage"` (la última aplicada — `marketing` fue el módulo #8). Crea `calendar_connection` + `calendar_source` con los UNIQUE PARCIALES dialect-agnósticos (postgresql_where + sin sqlite_where en la migración — el smoke usa el ORM, pero acá se replica el patrón de `0024`). **Tablas NUEVAS y vacías → sin riesgo de FK huérfana** (a diferencia de la lección §20 de marketing, que agregaba un FK a una columna pre-existente).

```python
"""add calendar connection + source (integración de calendario externo, Fase 1)

Revision ID: 0025_calendar_connection
Revises: 0024_marketing_promotion_usage
Create Date: 2026-06-22 00:00:00

Crea `calendar_connection` (PK·A·SD·T — cuenta OAuth de la clínica; tokens en Secret
Manager, NO acá) + `calendar_source` (PK·A·SD·T — calendario→sede). 2 UNIQUE PARCIALES
(provider+email / connection+external_calendar, WHERE deleted_at IS NULL). FK real
calendar_source.branch_id → branch (RESTRICT, nullable). Tablas NUEVAS vacías → sin
riesgo de FK huérfana.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_calendar_connection"
down_revision: str | None = "0024_marketing_promotion_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── CalendarConnection (PK·A·SD·T) ──
    op.create_table(
        "calendar_connection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("account_email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("secret_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="connected"),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_calendar_connection_provider_email",
        "calendar_connection",
        ["provider", "account_email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── CalendarSource (PK·A·SD·T) ──
    op.create_table(
        "calendar_source",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("calendar_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("external_calendar_name", sa.String(length=255), nullable=False),
        sa.Column(
            "branch_id",
            sa.String(length=36),
            sa.ForeignKey("branch.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_calendar_source_connection", "calendar_source", ["connection_id"])
    op.create_index("ix_calendar_source_branch", "calendar_source", ["branch_id"])
    op.create_index(
        "uq_calendar_source_connection_external",
        "calendar_source",
        ["connection_id", "external_calendar_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_calendar_source_connection_external", table_name="calendar_source")
    op.drop_index("ix_calendar_source_branch", table_name="calendar_source")
    op.drop_index("ix_calendar_source_connection", table_name="calendar_source")
    op.drop_table("calendar_source")
    op.drop_index("uq_calendar_connection_provider_email", table_name="calendar_connection")
    op.drop_table("calendar_connection")
```

> **F2 NO lleva migración** (`list_events` + `GET /external-events` + overlay son código puro; la lectura es on-demand sin tabla espejo). La tabla `ExternalEvent` (espejo cacheado con `sync_token`/`channel_id`) es de la **fase de sync diferida (B3)** — documentada en README/design, NO se crea aquí.

## Fases (resumen backend)

- **F0 Prep** (sin migr): 4 perms `CALENDAR_*` + subsets de rol (forward-declarados) en seed; Settings (6 vars + `_enforce_calendar_oauth`); paquete backend **INERTE** (NO registrado en `modules/__init__.py`/`main.py`). Smoke: rutas `/calendar/*` → 404. Molde scheduling F0.
- **F1 Conexión + mapeo** — `0025_calendar_connection`: modelos + `enums.py` + `services/providers/` (base + google + microsoft + factory, métodos `build_auth_url`/`exchange_code`/`refresh`/`list_calendars`) + `secrets.put` + `services/oauth.py` (start/callback) + `services/connection.py` + `services/source.py` (replace atómico) + routers + registrar el módulo. Smoke: el OAuth real NO se ejercita (ENV=dev, credenciales vacías); se testean los guards de dominio (404/409/`BRANCH_NOT_FOUND`) con la BD limpia.
- **F2 Lectura informativa** (sin migr): `list_events` en los adaptadores + `services/external_read.py` (`read_external_events` best-effort) + `GET /external-events`. El overlay y el aviso del wizard son frontend (ver [`frontend.md`](frontend.md)). Smoke: `/external-events` con BD limpia → `{events:[], sources_health:[]}` (sin conexiones, 200).
- **Diferidas (B1-B4)**: B1 modo bloqueante (`get_busy` → `busy` de `compute_available_slots`, extiende ADR-006); B2 per-doctor + push (`push_event/update_event/delete_event`, títulos PHI-min); B3 sync (`watch/get_changes` + `ExternalEvent` + Cloud Tasks renovación); B4 CalDAV. **Documentadas como roadmap, NO construir.**

## Notas de implementación / gotchas

- **`httpx.AsyncClient`, NO el SDK sync de Google** (`google-api-python-client` es bloqueante → rompería el event loop async). `httpx` ya es dep — verificar `pyproject.toml`; el import va **lazy** dentro de cada método (igual que `OpenAIProvider` importa `AsyncOpenAI` dentro de `complete`) → el boot/smoke sin red no rompe.
- **Google "Testing" → refresh tokens de 7 días**: publicar la app OAuth "In production" (verificación de scope sensitive `calendar.readonly`) ANTES de confiar en el almacenamiento durable. Es un gate de días-semanas → arrancarlo temprano (ADR-014 Consequences).
- **`access_type=offline` + `prompt=consent`** (Google) son obligatorios para garantizar el `refresh_token`; sin `prompt=consent`, Google omite el refresh token si la cuenta ya consintió antes.
- **Microsoft re-emite el `refresh_token` en cada refresh** (Google NO) → en `MicrosoftGraphAdapter.refresh` guardar el `refresh_token` nuevo; en Google conservar el viejo.
- **TZ**: los eventos del provider llegan como **instantes** RFC3339 con offset → normalizar con `_as_utc` (mismo helper que `availability.py`; no hay resolución de hora de pared como en `OperatingHours`). El render UTC→hora local del navegador lo hace el front con los helpers `calendarWeek.ts` (igual que las citas; render en la TZ de la sede = mejora diferida conjunta).
- **Aislamiento §23**: `read_external_events` NUNCA propaga un 5xx; un provider caído marca `sources_health` y sigue. Es el contrato que hace la capa puramente aditiva (un calendario externo caído no rompe la grilla ni la reserva).
- **Validar el FK ANTES del insert** (§20/§22): `replace_sources` valida cada `branch_id` no-NULL contra `clinic.branch` vivo (404 `BRANCH_NOT_FOUND`, no un 500 por el constraint).
- **`secrets.put` requiere `secretmanager.admin`** en la SA de Cloud Run (hoy solo tiene `secretAccessor`) — sumarlo al provisioning, lección de deploy.
- **El cliente OAuth (client_id/secret) es global por entorno**, NO por conexión (single-tenant, modelo Cal.com). Solo los **tokens** van por-conexión a Secret Manager.
