"""
Harness síncrono para los escenarios pytest-bdd.

pytest-bdd ejecuta los pasos de forma SÍNCRONA (no await-ea funciones async),
así que no podemos usar el fixture `client` async del conftest raíz. En su lugar
`bdd_client` corre el `AsyncClient` contra la app FastAPI en un event loop
dedicado, sobre una BD SQLite en memoria sembrada con el admin bootstrap. Así los
pasos Dado/Cuando/Entonces quedan síncronos y legibles.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import database as db_module
from app.core import seed as seed_module
from app.core.database import Base, get_db
from app.core.seed import seed
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


class SyncBddClient:
    """Adaptador síncrono sobre el AsyncClient de httpx para usar en pasos pytest-bdd."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._setup())

    async def _setup(self) -> None:
        self._engine = create_async_engine(TEST_DB_URL, future=True)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._sf = async_sessionmaker(self._engine, expire_on_commit=False, class_=AsyncSession)

        async def _override_get_db():
            async with self._sf() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_get_db
        db_module.AsyncSessionLocal = self._sf
        seed_module.AsyncSessionLocal = self._sf
        await seed()
        self._ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        return self._loop.run_until_complete(self._ac.request(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._loop.run_until_complete(self._ac.aclose())
        self._loop.run_until_complete(self._engine.dispose())
        app.dependency_overrides.clear()
        self._loop.close()


@pytest.fixture
def bdd_client() -> Iterator[SyncBddClient]:
    sync_client = SyncBddClient()
    try:
        yield sync_client
    finally:
        sync_client.close()


@pytest.fixture
def bdd_admin() -> dict[str, str]:
    return {"email": "admin@example.com", "password": "ChangeMe123!"}
