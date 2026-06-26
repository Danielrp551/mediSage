# medisage

medisage es una plataforma web que permite a clínicas especializadas ambulatorias crear y operar
chatbots conversacionales sobre WhatsApp para atender pacientes y gestionar reservas de citas, con
un panel administrativo y tableros de resultados.

**Stack:** Next.js 16 y React 19 (frontend, en Vercel) con FastAPI y SQLAlchemy 2.0 async
(backend, en Cloud Run) sobre PostgreSQL 16 (Cloud SQL) y Firestore, con autenticación JWT en
cookies httpOnly y control de acceso por roles (RBAC).

> El repositorio se construyó sobre una plantilla reutilizable interna y conserva el nombre
> `saya-template-stack` por legado; el producto que contiene es medisage. El manual técnico
> consolidado está en [docs/MANUAL_TECNICO.md](docs/MANUAL_TECNICO.md).

## Estructura del repositorio

```
saya-template-stack/
├── backend/                  FastAPI (Python 3.11)
│   ├── app/
│   │   ├── main.py           crea la app, middleware y routers (prefijo /api/v1)
│   │   ├── core/             config, db, security, seed, exceptions, firestore, cloud_tasks, secrets
│   │   ├── shared/           mixins, BaseRepository, esquemas base, query_builder
│   │   ├── middleware/       contexto de request (X-Request-ID)
│   │   ├── routers/          webhooks de WhatsApp (sin RBAC, firma HMAC)
│   │   └── modules/          11 módulos: admin, catalog, clinic, staff, crm, conversations,
│   │                         bots, scheduling, marketing, calendar, dashboards
│   │                         (cada módulo: models, schemas, repositories, services, routers)
│   ├── alembic/              migraciones de base de datos (0001 a 0026)
│   ├── tests/                pytest (unitarias e integración) y features/ (BDD con pytest-bdd)
│   ├── pyproject.toml        dependencias y configuración de herramientas
│   ├── Dockerfile            imagen multi-stage para Cloud Run
│   └── .env.example          plantilla de variables de entorno del backend
├── frontend/                 Next.js 16 (App Router)
│   ├── src/                  app/, actions/, components/, hooks/, lib/, services/, types/
│   ├── package.json
│   ├── vercel.json           cabeceras de seguridad y región de despliegue
│   └── .env.example          plantilla de variables de entorno del frontend
├── docs/                     documentación (ver la sección Documentación)
├── .github/workflows/        CI/CD: backend-ci, frontend-ci, deploy-backend-qa, deploy-backend-prod
├── docker-compose.yml        entorno local (Postgres y backend)
├── firebase.json             despliegue de las reglas de Firestore
└── firestore.rules           reglas de seguridad del read-model de conversaciones
```

## Dependencias y prerrequisitos

Prerrequisitos:

- Docker Desktop (Postgres y backend en local).
- Node.js 20 o superior y npm (frontend).
- Python 3.11 (solo si se corre el backend sin Docker; rango soportado 3.11 a 3.12).

Dependencias del backend (declaradas en `backend/pyproject.toml`): FastAPI, Uvicorn, Pydantic v2,
SQLAlchemy 2.0 async, asyncpg, Alembic, PyJWT, passlib con bcrypt, slowapi, httpx, firebase-admin,
google-cloud-tasks, google-cloud-secret-manager, openai, anthropic, reportlab, openpyxl. Para
desarrollo: pytest (con asyncio, cov y bdd), ruff y mypy. Se instalan con `pip install -e ".[dev]"`.

Dependencias del frontend (declaradas en `frontend/package.json`): Next.js 16, React 19,
TypeScript, Fluent UI 9, TanStack Query, nuqs, react-hook-form, Zod y firebase (Web SDK). Se
instalan con `npm install`.

## Variables de entorno

Copiar las plantillas y completarlas según el entorno:

- **Backend** (`cp backend/.env.example backend/.env`). Variables principales: `ENV_NAME`, `DEBUG`,
  `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_HOST`, `DB_PORT`, `USE_UNIX_SOCKET` y `CLOUD_SQL_INSTANCE`
  (conexión a Cloud SQL), `SECRET_KEY` (firma de los JWT), `CORS_ORIGINS`, `SEED_ADMIN_EMAIL` y
  `SEED_ADMIN_PASSWORD`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` y `BOT_DEFAULT_MODEL` (motor del
  bot), `GCP_PROJECT_ID` y `FIRESTORE_DATABASE` (Firestore), `CLOUD_TASKS_QUEUE` y
  `BOT_DISPATCH_SECRET` (despacho del bot), `DASHBOARD_REFRESH_ENABLED` y `DASHBOARD_REFRESH_SECRET`
  (tableros), y los `*_OAUTH_*` del calendario externo. La lista completa, con el propósito y el
  valor por defecto de cada variable, está en `backend/.env.example` y en
  [docs/MANUAL_TECNICO.md](docs/MANUAL_TECNICO.md) sección 3.4.
- **Frontend** (`cp frontend/.env.example frontend/.env.local`). Variable principal: `BACKEND_URL`
  (solo servidor, la URL del backend que usa el servidor de Next.js). También `NEXT_PUBLIC_APP_URL`,
  `AUTH_COOKIE_SECURE`, `AUTH_COOKIE_DOMAIN` y la configuración pública `NEXT_PUBLIC_FIREBASE_*`.

En local, con `ENV_NAME=dev`, los validadores de arranque no exigen secretos; `docker-compose.yml`
ya inyecta los valores mínimos en el servicio del backend.

## Ejecución local (Docker Compose)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

docker compose up -d          # Postgres y backend (migraciones y seed corren al arrancar)
docker compose logs -f backend

cd frontend && npm install && npm run dev   # frontend en otra terminal
```

- API en `http://localhost:8080` (Swagger en `/docs`, ReDoc en `/redoc`).
- Aplicación en `http://localhost:3000`.
- Credenciales iniciales: `admin@example.com` / `ChangeMe123!` (configurables con `SEED_ADMIN_EMAIL`
  y `SEED_ADMIN_PASSWORD` en `backend/.env` antes del primer arranque).
- `docker compose down -v` detiene todo y borra el volumen de la base de datos.

La alternativa sin Docker (backend nativo) y los comandos de migración, pruebas y lint están en
[docs/SETUP.md](docs/SETUP.md).

## Documentación

- [docs/MANUAL_TECNICO.md](docs/MANUAL_TECNICO.md): manual técnico consolidado (arquitectura,
  instalación, CI/CD, despliegue a Google Cloud, respaldo y restauración).
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): capas, módulos y contratos.
- [docs/SETUP.md](docs/SETUP.md): instalación local detallada por sistema operativo.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): despliegue a Google Cloud, secretos y CI/CD.
- [docs/BRANCHING.md](docs/BRANCHING.md): estrategia de ramas y protecciones.
- [docs/HARDENING.md](docs/HARDENING.md): checklist de preproducción.
- [docs/PERMISSIONS.md](docs/PERMISSIONS.md): modelo RBAC y cómo agregar permisos.
- [docs/diagrams/](docs/diagrams/README.md): diagramas PlantUML (entidad-relación y de clases por módulo).
- [docs/decisions/](docs/decisions/README.md): registros de decisión de arquitectura (ADR-001 a ADR-015).

## Extender con un módulo nuevo

El módulo `admin` es el patrón de referencia. Para un módulo nuevo (por ejemplo `inventory`):

1. **Backend**: crear `backend/app/modules/inventory/{models,schemas,repositories,services,routers}/`.
   Importar los modelos en `backend/app/modules/__init__.py`, incluir el router en
   `backend/app/main.py`, crear la migración Alembic y agregar los permisos en
   `backend/app/core/seed.py`.
2. **Frontend**: crear `types/inventory.types.ts`, `lib/schemas/inventory.schema.ts`,
   `actions/inventory.actions.ts` y `app/(main)/inventory/page.tsx`.
3. **Pruebas**: un smoke test en `backend/tests/test_inventory/` que cubra el flujo principal con
   autenticación real.

El detalle del flujo está en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) y [CLAUDE.md](CLAUDE.md).
