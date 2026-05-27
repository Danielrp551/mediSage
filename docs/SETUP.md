# Setup local

## Prerrequisitos

- **Docker Desktop** (para Postgres + backend)
- **Node.js 20+** y **npm**
- **Python 3.11** (solo si vas a correr backend fuera de Docker)

## Opción A — todo con Docker (más rápido)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

docker compose up -d        # levanta Postgres + backend
cd frontend && npm install && npm run dev
```

- Backend: http://localhost:8080 — `/docs` y `/redoc` disponibles en dev.
- Frontend: http://localhost:3000
- Credenciales bootstrap: `admin@example.com` / `ChangeMe123!` (cambia `SEED_ADMIN_*` en `backend/.env` antes del primer arranque).

## Opción B — backend nativo (sin Docker)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # PowerShell
pip install -e ".[dev]"
cp .env.example .env

# Asegúrate de tener Postgres corriendo (Cloud SQL Proxy, brew, docker run, etc.)
alembic upgrade head
python -m app.core.seed
fastapi dev                       # alias de uvicorn con reload
```

## Comandos útiles

### Backend

```bash
# Migraciones
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1

# Tests
pytest                              # todos
pytest tests/test_admin/test_auth.py
pytest -k "test_login"

# Lint / typecheck
ruff check .
ruff format .
mypy app
```

### Frontend

```bash
npm run dev          # turbopack
npm run build
npm run lint
npm run typecheck
npm run format
```

## Crear un nuevo módulo

Ver [ARCHITECTURE.md](ARCHITECTURE.md) — sigue la convención de `app/modules/admin/`.

1. Backend: crea modelo + schema + repo + service + router. Importa el modelo en `modules/__init__.py`. Incluye el router en `main.py`. Crea la migración Alembic. Añade permisos en `seed.py`.
2. Frontend: crea types + zod schema + server action + server component (page) + client component.
3. Tests: agrega un smoke test que cubra login → endpoint principal.
