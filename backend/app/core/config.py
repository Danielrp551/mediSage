"""
Centralized settings — read once from env / `.env`.
All env vars in the app go through here (no direct `os.getenv` elsewhere).
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "change-me"
_MIN_SECRET_LEN = 32


class Settings(BaseSettings):
    # ── General ──
    PROJECT_NAME: str = "Bold Template Stack"
    ENV_NAME: str = "dev"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # ── Server ──
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # ── Database (PostgreSQL) ──
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "bold_template"
    DB_ECHO: bool = False
    USE_UNIX_SOCKET: bool = False
    CLOUD_SQL_INSTANCE: str = ""

    # ── Security ──
    SECRET_KEY: str = _DEFAULT_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # JWT `iss` / `aud` claims — set per environment so a token leaked from
    # qa can't be replayed against prod (and vice-versa).
    JWT_ISSUER: str = "bold-template-stack"
    JWT_AUDIENCE: str = "bold-template-stack"

    # ── CORS ──
    CORS_ORIGINS: str = "http://localhost:3000"

    # ── Rate limit (per slowapi syntax: "<N>/<minute|hour|day>") ──
    LOGIN_RATE_LIMIT: str = "5/minute"
    # Refresh + logout are authenticated by token, but the endpoint itself is
    # unauthenticated (you POST a token). Throttle to slow credential-stuffing.
    AUTH_BURST_RATE_LIMIT: str = "30/minute"
    # Honour `X-Forwarded-For` for the rate-limit key. Set True only when the
    # app is behind a trusted LB (Cloud Run, Vercel proxying, ALB, etc.) —
    # outside that topology, any client can spoof the header and bypass limits.
    RATE_LIMIT_TRUST_FORWARDED: bool = False

    # ── Seed ──
    SEED_ADMIN_EMAIL: str = "admin@example.com"
    SEED_ADMIN_PASSWORD: str = "ChangeMe123!"

    # ── GCP / secrets / messaging (conversations module, ADR-010 / ADR-011) ──
    # GCP project for Secret Manager (per-account WhatsApp creds) + Firebase Admin.
    GCP_PROJECT_ID: str = ""
    # Firestore named database (read-model, ADR-011). Empty → backend elige por
    # ENV_NAME (`firestore._DB_BY_ENV`); puede fijarse explícito (ej. "medisage-qa").
    FIRESTORE_DATABASE: str = ""
    # Fallback de credenciales WhatsApp para local/dev (cuando ChannelAccount.secret_name
    # es NULL o USE_LOCAL_SECRETS). Defaults vacíos → en prod se resuelven por
    # Secret Manager (ADR-010); el smoke (ENV_NAME=dev) usa estos sin tocar el SDK.
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    # Versión de la Graph API de Meta para el outbound (F3). Configurable por env para
    # subir de versión sin redeploy de código (reconciliación #11). Default a una versión
    # GA estable; el endpoint de mensajes (`/{ver}/{phone_number_id}/messages`) es estable
    # entre versiones. No es secreto.
    WHATSAPP_GRAPH_API_VERSION: str = "v22.0"
    # Forzar el fallback a env (saltarse Secret Manager) aun fuera de dev — útil para
    # una cuenta única local o tests de integración sin GCP.
    USE_LOCAL_SECRETS: bool = False

    # ── Bots (módulo #6, ADR-005 / ADR-012) ──
    # Motor embebido multi-proveedor (default OpenAI). Las API keys son globales por
    # entorno (vía --set-secrets de Cloud Run); resolución per-bot vía secret_resolver
    # (ADR-010) = futuro. Defaults vacíos → inertes hasta F3 (el engine).
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    BOT_DEFAULT_MODEL: str = "gpt-4.1-mini"  # default de BotConfigurationVersion.model_name
    # Corta el loop de tool-calling de un turno (anti-runaway / cost guard).
    MAX_TOOL_ITERATIONS_PER_TURN: int = 5
    # Cloud Tasks: el turno del bot se despacha async (ADR-012). El webhook encola →
    # POST {SERVICE_BASE_URL}/api/v1/bots/engine/dispatch. Auth del dispatch (F3b) = SHARED-SECRET
    # (BOT_DISPATCH_SECRET, comparado en tiempo constante): el servicio es público (--allow-unauthenticated
    # por Meta/Vercel) → OIDC degradaría a verificación in-app sin el rechazo de la plataforma, sumando
    # fallas solo-en-prod (cert-fetch/clock-skew/audiencia/IAM actAs). OIDC = hardening futuro si el
    # endpoint se separa a un Cloud Run privado. Defaults vacíos → el auto-path es NO-OP (no se encola).
    CLOUD_TASKS_QUEUE: str = ""  # ej. medisage-bot-turns-qa
    CLOUD_TASKS_LOCATION: str = "us-central1"
    CLOUD_TASKS_INVOKER_SA: str = (
        ""  # reservado para OIDC futuro (no usado por el shared-secret MVP)
    )
    SERVICE_BASE_URL: str = (
        ""  # URL pública del Cloud Run (target del dispatch; sin trailing slash)
    )
    BOT_DISPATCH_SECRET: str = (
        ""  # shared-secret del endpoint /engine/dispatch (Secret Manager por env)
    )

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy connection string. Switches to Unix socket on Cloud Run."""
        if self.USE_UNIX_SOCKET and self.CLOUD_SQL_INSTANCE:
            return (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@/{self.DB_NAME}?host=/cloudsql/{self.CLOUD_SQL_INSTANCE}"
            )
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse `CORS_ORIGINS` (JSON array, CSV, or '*') into a list."""
        raw = self.CORS_ORIGINS.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [o.strip() for o in parsed if o.strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Validators ───────────────────────────────
    # Defense against silent misconfiguration. Both run after env parsing.

    @model_validator(mode="after")
    def _enforce_secret_key(self) -> Settings:
        """Outside `dev`, refuse to boot with the default or an obviously short key."""
        if self.ENV_NAME == "dev":
            return self
        if self.SECRET_KEY == _DEFAULT_SECRET:
            raise ValueError(
                f"SECRET_KEY is the default value. Set a real secret for ENV_NAME={self.ENV_NAME!r} "
                "(generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))')."
            )
        if len(self.SECRET_KEY) < _MIN_SECRET_LEN:
            raise ValueError(
                f"SECRET_KEY is too short ({len(self.SECRET_KEY)} chars); need >= {_MIN_SECRET_LEN}."
            )
        return self

    @model_validator(mode="after")
    def _forbid_cors_wildcard_with_credentials(self) -> Settings:
        """`CORS_ORIGINS='*'` + `allow_credentials=True` is rejected by Starlette at runtime,
        which manifests as a confusing CORS error. Catch it at boot."""
        origins = self.cors_origins_list
        if "*" in origins and len(origins) >= 1:
            raise ValueError(
                "CORS_ORIGINS contains '*' but the app sends credentials (httpOnly cookies). "
                "List explicit origins (comma-separated) or a JSON array."
            )
        return self

    @model_validator(mode="after")
    def _enforce_bot_dispatch_secret(self) -> Settings:
        """Si el auto-path del bot está habilitado (`CLOUD_TASKS_QUEUE` seteado), fuera de `dev` el
        endpoint interno `/engine/dispatch` (ADR-012) DEBE tener un `BOT_DISPATCH_SECRET` real: es la
        ÚNICA barrera entre internet y la ejecución del LLM (el servicio es público). Falla RUIDOSA al
        boot ante un secret vacío/corto en vez de aceptar dispatches sin auth o rechazarlos en silencio
        (lección operativa: nada que solo falle en prod)."""
        if self.ENV_NAME == "dev" or not self.CLOUD_TASKS_QUEUE:
            return self
        if len(self.BOT_DISPATCH_SECRET.strip()) < _MIN_SECRET_LEN:
            raise ValueError(
                "CLOUD_TASKS_QUEUE is set (bot auto-dispatch enabled) but BOT_DISPATCH_SECRET is "
                f"missing or too short (need >= {_MIN_SECRET_LEN} chars) for ENV_NAME="
                f"{self.ENV_NAME!r}. Set the per-environment secret (generate with: python -c "
                "'import secrets; print(secrets.token_urlsafe(48))')."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Singleton — cached to avoid re-reading `.env` per request."""
    return Settings()
