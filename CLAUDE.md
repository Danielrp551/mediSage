# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es este repositorio

**Template reutilizable**, no un producto final. Cada nueva app interna del equipo se inicia clonando esta plantilla y agregando módulos de dominio sobre ella. Cualquier cambio a este repo afecta a todos los proyectos que se generen a futuro — **antes de agregar algo, preguntar si pertenece a este template (reusable para cualquier app) o al proyecto derivado (específico al dominio)**.

El template ya trae auth + RBAC + CRUD de usuarios/roles/permisos listo para producción. El módulo `admin` es el patrón de referencia para nuevos módulos.

## Stack y targets

| Capa | Tecnología | Versión clave | Deploy target |
|---|---|---|---|
| Frontend | Next.js (App Router) + React | 16.x / 19.x | Vercel |
| Backend | FastAPI + SQLAlchemy 2.0 async | Python 3.11 | Cloud Run |
| DB | PostgreSQL | 16 | Cloud SQL (Postgres via unix socket) |
| Auth | JWT en cookies httpOnly + RBAC | — | — |
| Tooling | Docker Compose (local) · GitHub Actions (CI/CD) | — | — |

Hay tres CLAUDE.md: este (raíz, cross-cutting), `backend/CLAUDE.md` (FastAPI) y `frontend/CLAUDE.md` (Next.js). Para trabajo dentro de una de esas carpetas, leer también el específico.

## Comandos desde la raíz

```bash
# Stack local completo (Postgres + backend con reload). Frontend va aparte.
docker compose up -d
docker compose logs -f backend
docker compose down -v          # -v borra el volumen de la BD

# Frontend (terminal separada)
cd frontend && npm install && npm run dev
```

- API: http://localhost:8080 — Swagger UI en `/docs`, ReDoc en `/redoc`
- App: http://localhost:3000
- Credenciales bootstrap: `admin@example.com` / `ChangeMe123!` (configurables vía `SEED_ADMIN_*` en `backend/.env`)

Comandos por capa están en `backend/CLAUDE.md` y `frontend/CLAUDE.md` respectivamente. Los más usados desde la raíz son los de Docker Compose.

## Arquitectura de alto nivel

```
Browser ──HTTPS+cookie─▶ Next.js (Vercel) ──Bearer JWT (server-only)─▶ FastAPI (Cloud Run) ──unix socket─▶ Cloud SQL
```

**Reglas que rigen la frontera entre capas:**

- El **browser nunca habla con FastAPI directamente.** Todas las llamadas al backend salen desde el server de Next.js. Eso permite que `BACKEND_URL` y el JWT vivan solo del lado servidor.
- El **JWT vive en cookie httpOnly**, no en localStorage. El cliente JS no puede leerlo. Lo lee Next en sus Server Actions / Server Components y lo inyecta como `Authorization: Bearer …` al llamar a FastAPI.
- **El backend es la fuente de verdad de los permisos.** El frontend solo pre-filtra UX (esconde botones, redirige). Nunca se asume que ocultar un botón es suficiente — el backend rechaza con 403 sin importar lo que el front haya hecho.
- **Los permisos viajan en el access token** como claim `permissions[]`. No se consulta la BD por request. Implicancia: si revocas un permiso a un usuario activo, el cambio surte efecto al siguiente refresh (≤15 min default) o cuando se revoque la familia de refresh tokens.

Diagramas de clases y ER en [`docs/diagrams/`](docs/diagrams/README.md) (PlantUML). Decisiones técnicas en [`docs/decisions/`](docs/decisions/README.md).

## Contratos cross-cutting (back ↔ front)

Estos contratos deben respetarse a ambos lados — romper uno requiere actualizar back **y** front en el mismo PR:

| Contrato | Backend | Frontend |
|---|---|---|
| **Envelopes de respuesta** | `SingleResponse[T]` (`{success, data}`), `PaginatedResponse[T]` (`{success, data: {items, total, skip, limit}}`) en `app/shared/base_schemas.py` | Tipos espejo en `src/types/api.types.ts` |
| **Listados paginados** | `POST /<recurso>/list` recibe `QueryRequest` (pagination + sorting + grupos AND/OR de `FilterCondition`); `BaseRepository.get_paginated` lo aplica con `ALLOWED_FIELDS` como whitelist | `QueryParamsBuilder` construye el body; `useTableQuery` + URL state (`nuqs`) sincronizan paginación/filtros/sort |
| **Errores** | Lanzar excepciones de dominio (`NotFoundException`, `AlreadyExistsException`, `BadRequestException`, `UnauthorizedException`, `ForbiddenException`) — **nunca `HTTPException`** directo. El handler global las traduce a `{success: false, detail, code?, errors?}` | El backend client (`services/backend.client.ts`) inspecciona el envelope y lanza un error tipado |
| **Datetimes** | `timestamptz` en Postgres (UTC en disco), `datetime` tz-aware en Python, ISO 8601 con offset (`+00:00`) en JSON | `new Date()` parsea nativamente; `lib/utils/date.ts` formatea en locale del usuario |
| **Validación** | Pydantic v2 schemas en `<modulo>/schemas/` | Zod schemas en `src/lib/schemas/` — duplicados pero pequeños; deben coincidir |
| **Permisos** | `RequirePermission("CODE")` como `Depends(...)` en el router; el code es un string atómico (`USERS_CREATE`) | `<PermissionGuard anyOf={...}>` para UI, `requirePermission()` en RSC para redirect |

## Auth flow (lo crítico)

- **Access token (15 min)** lleva `roles[]` y `permissions[]` en los claims → enforcement O(1) sin DB lookup.
- **Refresh token (7 d)** lleva `family` UUID. Cada refresh rota **ambos** tokens y mantiene la `family`. Logout o detección de reuso revoca la `family` en `revoked_token_family` → el siguiente refresh devuelve 401.
- **Cookies**: `AUTH_COOKIE_SECURE=true` en prod, `httpOnly`, `SameSite=Lax`. Path-scoped según `AUTH_COOKIE_DOMAIN`.

## Cómo extender el template (workflow nuevo módulo)

El módulo `admin` es la referencia. Para un módulo nuevo (p.ej. `inventory`):

**Backend** (`backend/app/modules/inventory/`):
1. `models/<entidad>.py` — heredar mixins (`PrimaryKeyMixin`, `ActiveMixin`, `SoftDeleteMixin`, `TimestampMixin`) + `Base`. Tablas de asociación M:N en `models/associations.py`.
2. `schemas/<entidad>.py` — Pydantic v2: `Create`, `Update`, `Item` (para listados), `Detail`, `Option` (para selects).
3. `repositories/<entidad>.py` — extender `BaseRepository[Model]`. Definir `ALLOWED_FIELDS` (whitelist para filter/sort dinámico). Agregar queries específicas si las hay (`get_by_email`, etc.).
4. `services/<entidad>.py` — **módulo de funciones** (no clases). Cada función recibe `AsyncSession` y devuelve un response schema. Lanzar excepciones de dominio, no `HTTPException`.
5. `routers/<entidad>.py` — endpoints FastAPI que delegan al service. `Depends(RequirePermission("..."))` por endpoint que requiere autorización.
6. Importar el módulo en `app/modules/__init__.py` y registrar el router en `app/main.py`.
7. `alembic revision --autogenerate -m "add inventory"` → revisar la migración generada antes de aplicar.
8. Agregar permisos del módulo a `app/core/seed.py:SEED_PERMISSIONS`.

**Frontend** (`frontend/src/`):
1. `types/inventory.types.ts` — espejo de los Pydantic schemas.
2. `lib/schemas/inventory.schema.ts` — Zod schemas para forms (compartidos cliente/servidor).
3. `actions/inventory.actions.ts` — Server Actions con `"use server"`. Llaman al backend client, hacen `revalidateTag(...)`.
4. `lib/constants/endpoints.ts` — agregar las URLs del nuevo recurso.
5. `lib/constants/navigation.ts` — agregar item con `permissions: ["MENU-INVENTORY"]`.
6. `app/(main)/inventory/page.tsx` — RSC con `await requirePermission("MENU-INVENTORY")` + prefetch de la primera página.
7. Si hay listado: client component con `useTableQuery` (patrón de `admin/users`).

**Tests**:
- `backend/tests/test_inventory/` — al menos un smoke test que cubra el path principal con autenticación real (no mockear DB; usar `aiosqlite` en memoria configurado en conftest).

**Documentación del módulo nuevo**:
- ADR en `docs/decisions/ADR-NNN-...md` si la decisión es no-obvia.
- Diagrama de clases / ER en `docs/diagrams/class-backend-<modulo>.puml` y `er-<modulo>.puml`. Renderizar con `java -jar tools/plantuml.jar -tsvg -o out docs/diagrams/*.puml`.

## Hardening pre-prod

`docs/HARDENING.md` lista 5 items que la plantilla **no** resuelve por sí sola (dependen de la infra real):

1. Rate limit distribuido en Redis (si `max-instances > 3`)
2. Pool de DB vs concurrency de Cloud Run (antes del primer load test)
3. Migraciones como Cloud Run Job (antes de la primera migración que tarda > 30 s)
4. Cloud Run deploy flags (`--service-account`, `--execution-environment`, `--ingress`) — **no postergar**, el SA default tiene permisos Editor
5. Argon2id en lugar de bcrypt (si las credenciales son de alto valor)

Si vas a desplegar a prod, revisar `docs/HARDENING.md` antes.

## Convenciones que aplican en todo el repo

- **Soft delete vs disable**: dos cosas distintas. `deleted_at` (SoftDeleteMixin) es eliminación lógica filtrada por defecto en todos los reads del `BaseRepository`. `active` (ActiveMixin) es un toggle de negocio "habilitado/deshabilitado". No confundir.
- **`ALLOWED_FIELDS` en cada repositorio** es el whitelist de columnas que pueden usarse para filtrar/ordenar dinámicamente. Si no está, no se permite. Esto previene que el frontend filtre por columnas privadas (p.ej. `password_hash`).
- **Audit columns (`created_by`, `updated_by`)** se pasan explícitamente desde los services (que conocen al actor). No son automáticos. Esto deja la traza honesta.
- **Idiomas**: comentarios y docs en español, identificadores en inglés. Mantener la convención al escribir nuevos archivos.
- **Logs**: JSON estructurado con `X-Request-ID` por request (middleware en `app/middleware/request_context.py`). No usar `print()`.

## Documentos relacionados

- [README.md](README.md) — vista de marketing del template
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — capas, módulos, contratos (narrativa)
- [docs/SETUP.md](docs/SETUP.md) — setup detallado por sistema operativo
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Cloud Run + Vercel + secretos + CI/CD
- [docs/PERMISSIONS.md](docs/PERMISSIONS.md) — modelo RBAC y cómo agregar permisos
- [docs/HARDENING.md](docs/HARDENING.md) — checklist pre-prod (5 items)
- [docs/diagrams/](docs/diagrams/README.md) — diagramas PlantUML (class, ER, sequence, …)
- [docs/decisions/](docs/decisions/README.md) — Architecture Decision Records
- [backend/CLAUDE.md](backend/CLAUDE.md) — específico de FastAPI
- [frontend/CLAUDE.md](frontend/CLAUDE.md) — específico de Next.js
