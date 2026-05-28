"""
Pytest fixtures.

Tests run against an in-memory SQLite via aiosqlite — fast and isolated.
The `app` and `client` fixtures override the production DB dependency
so the same FastAPI app instance can be exercised end-to-end.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

# Test-only env. Must be set BEFORE importing the app.
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-entropy-for-jwt-signing")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "5")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "1")
os.environ.setdefault("LOGIN_RATE_LIMIT", "1000/minute")
os.environ.setdefault("AUTH_BURST_RATE_LIMIT", "1000/minute")
os.environ.setdefault("DEBUG", "True")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.seed import seed
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    # Seed the bootstrap admin into the test DB so login tests can run.
    # The seed uses its own session factory (AsyncSessionLocal) so we
    # patch it for the test DB just in time.
    from app.core import database as db_module
    from app.core import seed as seed_module

    db_module.AsyncSessionLocal = session_factory
    seed_module.AsyncSessionLocal = session_factory
    await seed()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def admin_credentials() -> dict[str, str]:
    return {"email": "admin@example.com", "password": "ChangeMe123!"}
