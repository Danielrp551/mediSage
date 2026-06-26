# Arquitectura

> **Diagramas detallados** → [`diagrams/`](diagrams/README.md) (ER, class, sequence, C4 en Mermaid).
> **Decisiones técnicas** → [`decisions/`](decisions/README.md) (por qué cookies httpOnly, por qué 5 capas, etc.).

Este documento da la vista narrativa. Para profundizar en cada pieza, ir a los diagramas o ADRs enlazados.

## Vista general

```
┌──────────────┐  HTTPS + httpOnly cookies   ┌──────────────────────┐
│   Browser    │ ◀──────────────────────────▶│  Next.js (Vercel)    │
└──────────────┘                              │  • RSC + Server Actions
                                              │  • middleware (edge)  │
                                              │  • BACKEND_URL (svr)  │
                                              └──────────┬───────────┘
                                                         │ Bearer (server-only)
                                                         ▼
                                              ┌──────────────────────┐
                                              │  FastAPI (Cloud Run) │
                                              │  • RBAC + JWT        │
                                              │  • Alembic           │
                                              └──────────┬───────────┘
                                                         │ unix socket
                                                         ▼
                                              ┌──────────────────────┐
                                              │ Cloud SQL Postgres   │
                                              └──────────────────────┘
```

**Browser ↔ Next.js**: cookies httpOnly. Las llamadas a backend nacen siempre desde el servidor de Next, nunca desde el cliente. El bundle de cliente jamás contiene `BACKEND_URL` ni el JWT.

**Next.js ↔ FastAPI**: el backend client (`services/backend.client.ts`) lee la cookie de la request actual con `cookies()`, inyecta `Authorization: Bearer …`, y refresca automáticamente con un único reintento en 401.

## Backend — 5 capas

```
app/
├── main.py                      Crea FastAPI, registra middleware/handlers/routers
├── core/                        Cross-cutting (config, db, security, logging, seed, exceptions, dependencies)
├── shared/                      Mixins, BaseRepository, BaseSchemas, query_builder, utils
├── middleware/                  RequestContextMiddleware (X-Request-ID)
└── modules/
    └── <domain>/
        ├── models/              SQLAlchemy ORM, una entidad por archivo + associations.py
        ├── schemas/             Pydantic v2 request/response
        ├── repositories/        Async CRUD; extienden BaseRepository, definen ALLOWED_FIELDS
        ├── services/            Lógica pura (validaciones, transacciones, orquestación)
        └── routers/             Endpoints FastAPI; delegan a services
```

### Reglas

- **Routers** solo validan tipos y delegan. No usan SQLAlchemy directo.
- **Services** lanzan `NotFoundException / AlreadyExistsException / BadRequestException / UnauthorizedException / ForbiddenException`. Nunca `HTTPException`.
- **Repositories** extienden `BaseRepository[Model]`. `ALLOWED_FIELDS` es el whitelist para filtros/sort dinámicos.
- **Modelos** usan los mixins de `app/shared/base_model.py`: `PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin`.

### Auth + RBAC

- **Access token (15 min)** lleva claims `roles[]` y `permissions[]` para que el enforcement sea O(1) sin tocar BD.
- **Refresh token (7 d)** lleva `family` UUID. Cada refresh rota ambos tokens manteniendo el `family`. Logout o reuso revoca la familia en `revoked_token_family` y el siguiente refresh devuelve 401.
- **`RequirePermission("CODE")`** es una dependency factory:
  ```python
  @router.post("", dependencies=[Depends(RequirePermission("USERS_CREATE"))])
  ```
- **`CurrentUser`** (Annotated alias) decodifica + carga el `User` desde BD y stashea los claims en `user._token_permissions`.

## Frontend — App Router

```
src/
├── app/                         Routes
│   ├── (auth)/login/            Public — RSC checks "already signed in" and skips
│   ├── (main)/...               Protected by middleware.ts + requireAuth() in each layout
│   ├── error.tsx / not-found.tsx
│   └── layout.tsx               Loads /auth/me, hydrates AuthProvider with initial user
├── actions/                     Server Actions ("use server")
├── components/                  ui/, layout/, guards/
├── hooks/                       useAuth, usePermissions, useTableQuery
├── lib/
│   ├── auth/{session,jwt}.ts    server-only session helpers
│   ├── constants/               endpoints, navigation, cookies
│   ├── schemas/                 Zod — usados por forms y por Server Actions (revalidación)
│   └── utils/                   query-builder, date, cn
├── providers/                   AppProviders, AuthProvider
├── services/backend.client.ts   server-only HTTP a FastAPI (con auto-refresh)
└── types/                       espejo de los Pydantic schemas
```

### Server vs Client

- **Server Components** = páginas (`page.tsx`), layouts, todo lo que llama al backend. Prefetch + permission check.
- **Client Components** = formularios, tablas con paginación dinámica, drawers. Importan `@/actions/*` (Server Actions) o `@/hooks/*`.

### State

- **URL** (`nuqs`) para paginación + filtros + sort. Sobrevive a refresh y permite compartir links.
- **TanStack Query** para cache + refetch tras mutaciones.
- **AuthProvider** (Context) hidratado en el server con `AuthenticatedUser`. UI gating con `usePermissions()`.
- **httpOnly cookies** para tokens. No localStorage.

## Contratos entre frontend y backend

- **`QueryRequest`** (`POST /…/list`) — paginación + sorting + grupos AND/OR de `FilterCondition`. Frontend construye con `QueryParamsBuilder`, backend ejecuta con `BaseRepository.get_paginated` + `apply_filters`.
- **`SingleResponse[T]` / `PaginatedResponse[T]`** — todos los recursos van envueltos en `{success, data}` o `{success, data: {items, total, skip, limit}}`. Tipos espejo en `frontend/src/types/api.types.ts`.
- **Errores** — `{success: false, detail, code?, errors?}` con status code adecuado.
- **Datetimes** — `timestamptz` en Postgres (UTC en disco), `datetime` tz-aware en Python, ISO 8601 con offset (`+00:00`) en JSON. JavaScript `new Date()` lo parsea nativamente; `lib/utils/date.ts` renderiza en locale del usuario.
