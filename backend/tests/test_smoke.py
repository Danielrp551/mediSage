"""Smoke: the app boots and the health endpoint answers."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


async def test_docs_available_in_debug(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
