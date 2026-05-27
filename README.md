# Bold Template Stack

Plantilla reutilizable Bold para arrancar nuevas apps internas: **Next.js 16 + React 19 + FastAPI + PostgreSQL + Cloud Run + Vercel**, con autenticación + RBAC + CRUD de usuarios/roles/permisos listos para producción.

## ¿Qué incluye?

- **Backend FastAPI** (Python 3.11, SQLAlchemy 2.0 async, Pydantic v2)
  - Arquitectura modular 5-capas: `models / schemas / repositories / services / routers`
  - JWT con rotación de refresh + revocación por familia
  - **RBAC con `RequirePermission()` aplicado en el backend** (los permisos viajan en el access token)
  - Soft delete (`deleted_at`) automático en `BaseRepository`
  - Repositorio paginado con filtros dinámicos y whitelist por entidad
  - Rate limiting en `/auth/login` (slowapi)
  - Logging JSON estructurado con `X-Request-ID` por request
  - Alembic migraciones, seed idempotente, tests con pytest-asyncio
  - Dockerfile multi-stage listo para Cloud Run
- **Frontend Next.js 16 App Router**
  - **Cookies httpOnly** para tokens (el browser nunca ve el JWT)
  - **Edge middleware** protege `(main)` antes de renderizar
  - **Server Components** pre-cargan la primera página de cada listado
  - **Server Actions** + `revalidateTag` para mutaciones (Zod compartido cliente/servidor)
  - **TanStack Query** + `nuqs` (URL state) para paginación, filtros y sort
  - Fluent UI 9 + DataTable<T>, Drawer, Pagination, ConfirmDialog, PermissionGuard
  - react-hook-form + Zod en todos los formularios
- **Infra**
  - `docker-compose.yml` para dev local (Postgres + backend con reload)
  - GitHub Actions: `backend-ci` (ruff + pytest), `frontend-ci` (lint + tsc + build), `backend-deploy` (Cloud Run con Workload Identity Federation)
  - Vercel ready (frontend) con headers de seguridad

## Arranque rápido

```bash
# Backend + Postgres
docker compose up -d

# Frontend
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

- API en http://localhost:8080 (docs en `/docs`)
- App en http://localhost:3000
- Login con: `admin@example.com` / `ChangeMe123!` (configurable en `backend/.env`)

## Documentos

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — capas, módulos, contratos
- [docs/SETUP.md](docs/SETUP.md) — setup detallado por sistema
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Cloud Run + Vercel + secretos + CI
- [docs/PERMISSIONS.md](docs/PERMISSIONS.md) — modelo RBAC, cómo agregar permisos
- [docs/diagrams/](docs/diagrams/README.md) — diagramas Mermaid (ER, class, sequence, C4)
- [docs/adr/](docs/adr/README.md) — Architecture Decision Records (por qué se hizo así)

## Convención: extender la plantilla

Para un nuevo módulo de dominio (p. ej. `inventory`):

1. `backend/app/modules/inventory/{models,schemas,repositories,services,routers}/`
2. Agrégalo a `backend/app/modules/__init__.py`.
3. Incluye el router en `backend/app/main.py`.
4. Crea migración Alembic + permisos en `seed.py`.
5. Frontend: `actions/inventory.actions.ts`, `types/inventory.types.ts`, `app/(main)/inventory/page.tsx`.

El patrón de `admin/users` (page RSC con prefetch + client component con `useTableQuery`) es el referente.

