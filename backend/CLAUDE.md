# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Específico del backend. Para contratos cross-cutting (envelopes, auth flow end-to-end, cómo agregar un módulo completo), leer primero el [CLAUDE.md raíz](../CLAUDE.md).

## Stack

- **Python 3.11** (`requires-python = ">=3.11,<3.13"`)
- **FastAPI** + Pydantic v2 + Pydantic Settings
- **SQLAlchemy 2.0 async** (`asyncpg` en prod, `aiosqlite` en tests)
- **Alembic** para migraciones
- **PyJWT** + Passlib (bcrypt) para auth
- **slowapi** para rate limiting
- **ruff** (lint + format), **mypy** (`strict = true`)
- **pytest** + pytest-asyncio (`asyncio_mode = "auto"`)

Todas las deps están en `pyproject.toml`. Setup con `pip install -e ".[dev]"`.

## Comandos

```bash
# Servidor local (sin Docker; requiere Postgres corriendo)
fastapi dev                              # alias de uvicorn con reload
fastapi run                              # producción

# Migraciones
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1
alembic history

# Tests (aiosqlite in-memory; no requiere Postgres)
pytest                                   # todos
pytest tests/test_admin/test_auth.py     # un archivo
pytest tests/test_admin -v               # un directorio
pytest -k "test_login"                   # por nombre
pytest --cov=app --cov-report=term-missing

# Lint + format + typecheck
ruff check .
ruff check . --fix
ruff format .
mypy app
```

Línea: 100 chars (`ruff.line-length = 100`). `E501` (line too long) está ignorado pero mantener cerca de 100.

## Estructura en 5 capas

```
app/
├── main.py             FastAPI app, middleware, handlers, routers
├── core/               Cross-cutting: config, db, security, dependencies, seed, exceptions, rate_limit, logging
├── shared/             Mixins, BaseRepository, base_schemas, query_builder, utils
├── middleware/         RequestContextMiddleware
└── modules/<dominio>/
    ├── models/         SQLAlchemy ORM (una entidad por archivo; associations.py para M:N)
    ├── schemas/        Pydantic v2 (Create, Update, Item, Detail, Option)
    ├── repositories/   Extienden BaseRepository[Model]; definen ALLOWED_FIELDS
    ├── services/       Módulos de funciones (NO clases); lógica + validación + transacciones
    └── routers/        Endpoints FastAPI; validan tipos y delegan al service
```

### Reglas inviolables por capa

| Capa | DEBE | NO DEBE |
|---|---|---|
| **Routers** | Recibir `CurrentAuth` / `DBSession` / payloads Pydantic. Delegar al service. | Importar SQLAlchemy. Catchear excepciones de dominio. Construir respuestas a mano (los services devuelven el envelope). |
| **Services** | Recibir `AsyncSession` + payloads. Lanzar excepciones de dominio. Devolver `SingleResponse` / `PaginatedResponse`. | Lanzar `HTTPException` (handler global no la convierte al envelope `{success, detail, code}`). Hacer `commit` — `get_db` se encarga al final del request. |
| **Repositories** | Extender `BaseRepository[Model]`, definir `ALLOWED_FIELDS`, encapsular SQL específico (joins, eager load). | Saltarse `ALLOWED_FIELDS` (es el whitelist anti-leak). Mezclar lógica de negocio. |
| **Models** | Heredar `Base` + mixins (`PrimaryKeyMixin`, `ActiveMixin`, `SoftDeleteMixin`, `TimestampMixin`). Usar `Mapped[...]` + `mapped_column(...)`. | Tener métodos con efectos de BD. |
| **Schemas** | Pydantic v2 con tipos estrictos. Variantes: `Create` (input), `Update` (partial input), `Item` (listado), `Detail` (full), `Option` (selects). | Llevar lógica de dominio. |

## Excepciones de dominio (crítico)

**Nunca lanzar `HTTPException` directo desde un service.** Las excepciones de dominio viven en `app/core/exceptions.py`:

| Excepción | HTTP | Cuándo |
|---|---|---|
| `NotFoundException` | 404 | Recurso no existe |
| `AlreadyExistsException` | 409 | Conflicto por unicidad (email tomado, code duplicado) |
| `BadRequestException` | 400 | Input válido por tipo pero inválido semánticamente |
| `UnauthorizedException` | 401 | Credencial faltante/inválida/expirada |
| `ForbiddenException` | 403 | Autenticado pero sin permiso |

El handler global (`register_exception_handlers` en `main.py`) las convierte al envelope `{success: false, detail, code?, errors?}`. Todas pueden tomar un `code=` opcional (ej. `ForbiddenException(..., code="PERMISSION_DENIED")`) que el frontend usa para branching.

## Auth y RBAC

Detalle en [`docs/PERMISSIONS.md`](../docs/PERMISSIONS.md). Los puntos críticos para escribir código:

- **`CurrentAuth`** (alias `Annotated[AuthContext, Depends(get_auth)]`) carga el `User` + extrae `permissions` / `roles` del JWT. Los permisos del token son frozensets — comparaciones O(1).
  ```python
  async def me(auth: CurrentAuth) -> ...:
      return _serialize(auth.user)
  ```
- **`RequirePermission("CODE", "OTRO_CODE")`** es una *dependency factory* que exige **TODOS** los códigos. Aplicar como `dependencies=[Depends(RequirePermission("USERS_CREATE"))]` en el decorator del endpoint — no en el handler. El handler que necesita el actor recibe `CurrentAuth` aparte.
- **El token NO se consulta en BD por request.** `permissions` viajan en los claims. Para forzar logout, se revoca la `family` del refresh token (próxima rotación devuelve 401).
- **`actor_id`** se pasa explícitamente desde el router a los services. No es automático — eso mantiene la traza honesta (`created_by`, `updated_by`).

## Sesión de BD y transacciones

- **Una sesión por request.** `get_db()` (dependency) abre un `AsyncSession`, hace `commit` al final si todo OK, `rollback` si hubo excepción. **No llamar `session.commit()` desde un service** — duplica la transacción.
- Para forzar que SQLAlchemy emita SQL pendiente (p.ej. obtener un `id` después de un `add`), usar `await session.flush()`, no `commit()`.
- **Lazy loading**: por defecto `lazy="raise"` en las relaciones (evita N+1 silencioso). Las que se cargan eager se marcan `lazy="selectin"` (`User.roles`, `User.permissions`, `Role.permissions`). Si necesitas relaciones que están en `raise`, usar `selectinload(...)` explícito.
- **Soft delete**: `BaseRepository` filtra `deleted_at IS NULL` automáticamente en `get_by_id` y `get_paginated`. Para hard delete usar `db.delete(obj)`; para soft delete, `repo.soft_delete(obj)`.

## QueryRequest y `BaseRepository.get_paginated`

Listados dinámicos viajan como `POST /<recurso>/list` con body `QueryRequest`:

```jsonc
{
  "pagination": {"skip": 0, "limit": 10},
  "sorting": {"sort_by": "created_on", "sort_order": "desc"},
  "filters": {
    "filters": [
      {"operator": "AND", "conditions": [
        {"field": "email", "operator": "contains", "value": "@bold"},
        {"field": "active", "operator": "eq", "value": true}
      ]}
    ]
  }
}
```

- `BaseRepository.get_paginated` aplica filtros, sort y paginación contra `ALLOWED_FIELDS`. Campos fuera del whitelist se ignoran silenciosamente — **agregarlos a `ALLOWED_FIELDS` cuando expongas una nueva columna filtrable**.
- Operadores disponibles: `eq, neq, contains, starts_with, gt, gte, lt, lte`. Para agregar uno, actualizar `FilterOperator` (enum) Y `query_builder.apply_filters`.
- Eager loads se pasan vía `load=(selectinload(Model.rel),)` argument:
  ```python
  items, total = await user_repository.get_paginated(
      db, query_request,
      load=(selectinload(User.roles), selectinload(User.permissions)),
  )
  ```

## Settings (config centralizado)

- Toda config viene de `app/core/config.py:Settings` (Pydantic Settings). **No usar `os.getenv` en ningún otro lado.**
- `get_settings()` está `@lru_cache` — singleton.
- `database_url` cambia entre TCP local (`DB_HOST:DB_PORT`) y unix socket Cloud SQL (`USE_UNIX_SOCKET + CLOUD_SQL_INSTANCE`) automáticamente.
- Hay dos validadores `@model_validator(mode="after")`:
  - `SECRET_KEY` debe ser != `"change-me"` y ≥ 32 chars fuera de `dev`.
  - `CORS_ORIGINS = "*"` + cookies httpOnly se rechaza al boot.

## Migraciones (Alembic)

- `alembic/env.py` importa `app.modules` para que TODAS las tablas estén registradas antes de leer `Base.metadata`. Si agregas un módulo nuevo, asegúrate de que esté en `app/modules/__init__.py` o las migraciones autogeneradas no lo verán.
- Genera con `alembic revision --autogenerate -m "..."`. **Siempre revisar el script generado** — autogenerate no detecta cambios de tipo (`String(80)` → `String(120)`) ni renombrados (los ve como drop+create, perdiendo datos).
- En el Dockerfile, el `CMD` corre `alembic upgrade head && python -m app.core.seed` antes de uvicorn. Para migraciones > 30 s o `min-instances > 1` mover a Cloud Run Job (ver [`docs/HARDENING.md`](../docs/HARDENING.md) §3).

## Seed (`app/core/seed.py`)

- Idempotente con `ON CONFLICT DO NOTHING` — se ejecuta en cada arranque del Dockerfile, no rompe nada si ya está aplicado.
- Define los permisos canónicos del módulo `admin` y el usuario bootstrap (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`).
- **Para agregar permisos de un módulo nuevo**, añadirlos a `SEED_PERMISSIONS` (las apps derivadas seedean al primer arranque sin intervención manual).

## Tests

`tests/conftest.py` crea un `AsyncClient` que apunta al `app` real con un `AsyncSession` overrideado a **SQLite in-memory** (`aiosqlite`):

- Cada test arranca con BD limpia (engine por test, `Base.metadata.create_all`).
- El fixture `client` patchea `database.AsyncSessionLocal` y `seed.AsyncSessionLocal` al engine de test antes de correr `seed()`, así el admin bootstrap existe en cada test.
- Fixtures clave: `db_engine`, `session_factory`, `db_session`, `client`, `admin_credentials`.
- `conftest.py` setea env vars **antes de importar `app`**: `SECRET_KEY` de test, rate limits altos. Si añades una env var nueva con efecto al boot, sumar el default a `conftest.py`.

Ejemplo del patrón:
```python
async def test_admin_can_list_users(client, admin_credentials):
    login = (await client.post("/api/v1/admin/auth/login", json=admin_credentials)).json()
    token = login["tokens"]["access_token"]
    response = await client.post(
        "/api/v1/admin/users/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
```

## Patrones SQLAlchemy 2.0 a respetar

- Usar la sintaxis nueva: `Mapped[str] = mapped_column(...)` — no `Column(String, ...)` solo.
- `from __future__ import annotations` en TODOS los archivos del backend (resuelve circular imports en `relationship(...)` con strings).
- Asociaciones M:N van en `models/associations.py` (no en cada modelo) **para que SQLAlchemy las vea antes de los modelos que dependen de ellas**.
- `relationship(..., back_populates="...")` siempre con `back_populates`, no `backref`.
- Para listas de relaciones que casi nunca uses, `lazy="raise"` (default que aplicamos). Para las que sí uses al listar entidades, `lazy="selectin"`.

## Logging

- `app/core/logging.py:configure_logging` setea formato JSON estructurado.
- `app/middleware/request_context.py:RequestContextMiddleware` genera/propaga `X-Request-ID` y lo agrega a cada log line del request.
- **No usar `print()`**. Importar `logger = logging.getLogger(__name__)` en cada módulo que necesite logs.

## Rate limiting

- `slowapi` con storage in-memory (default) — funciona para `max-instances = 1`. Para escalar ver [`docs/HARDENING.md`](../docs/HARDENING.md) §1 (Redis).
- Endpoints sensibles (`/auth/login`, `/auth/refresh`, `/auth/logout`) ya tienen el decorator aplicado. `RATE_LIMIT_TRUST_FORWARDED` solo a `True` detrás de LB confiable.

## Para crear un módulo nuevo

El paso a paso completo (back + front + tests + docs) está en el [CLAUDE.md raíz](../CLAUDE.md#cómo-extender-el-template-workflow-nuevo-módulo). La versión solo-backend:

1. `app/modules/<x>/{models,schemas,repositories,services,routers}/`
2. Importar el subpaquete en `app/modules/__init__.py` (para que Alembic y los relationships lo registren).
3. Incluir el router en `app/main.py` o crear un agregador `app/modules/<x>/routers/__init__.py` como en `admin`.
4. `alembic revision --autogenerate -m "add <x>"` → **revisar** el script.
5. Agregar permisos del módulo a `app/core/seed.py:SEED_PERMISSIONS`.
6. Tests: al menos un smoke test en `tests/test_<x>/` que cubra login → endpoint principal.
