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


@lru_cache
def get_settings() -> Settings:
    """Singleton — cached to avoid re-reading `.env` per request."""
    return Settings()
