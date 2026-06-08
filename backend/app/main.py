"""
FastAPI application entrypoint.

Order of operations matters:
 1. configure_logging() — every log line below is structured.
 2. import `app.modules` — registers all SQLAlchemy models so relationships
    can resolve across modules before any query runs.
 3. middleware + handlers + routers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Side-effect: registers all ORM models.
from app import modules as _modules  # noqa: F401
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.middleware.request_context import RequestContextMiddleware
from app.modules.admin.routers import router as admin_router
from app.modules.bots.routers import router as bots_router
from app.modules.catalog.routers import router as catalog_router
from app.modules.clinic.routers import router as clinic_router
from app.modules.conversations.routers import router as conversations_router
from app.modules.crm.routers import router as crm_router
from app.modules.scheduling.routers import router as scheduling_router
from app.modules.staff.routers import router as staff_router
from app.routers.webhooks import router as webhooks_router

settings = get_settings()
configure_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# ── Rate limiting (slowapi) ────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Exception handlers ────────────────────────────
register_exception_handlers(app)

# ── Routers ───────────────────────────────────────
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog_router, prefix=settings.API_V1_PREFIX)
app.include_router(clinic_router, prefix=settings.API_V1_PREFIX)
app.include_router(conversations_router, prefix=settings.API_V1_PREFIX)  # /conversations interno
app.include_router(crm_router, prefix=settings.API_V1_PREFIX)
app.include_router(staff_router, prefix=settings.API_V1_PREFIX)
app.include_router(bots_router, prefix=settings.API_V1_PREFIX)  # /bots/configurations/... (F1)
app.include_router(
    scheduling_router, prefix=settings.API_V1_PREFIX
)  # /scheduling/appointment-statuses/... (F1)
# Webhooks top-level (sin JWT) — Meta/WhatsApp. Firma HMAC / verify token, no RBAC.
app.include_router(webhooks_router, prefix=settings.API_V1_PREFIX)  # /webhooks/whatsapp/{id}


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Cloud Run / load-balancer health probe."""
    return {"status": "ok", "env": settings.ENV_NAME}
