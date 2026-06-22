"""
Tests de integración del módulo bots — BotTool CRUD (catálogo de herramientas invocables).

Cubre el service `bot_tool` (CRUD + guard de unicidad 409 + denormalizado `is_registered`) vía la
API pública. Las tools seedeadas (`_seed_bot_tools`) ya existen, por eso estos tests usan codes
nuevos y propios.
"""

from __future__ import annotations

from httpx import AsyncClient

PREFIX = "/api/v1/bots"


async def _token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post("/api/v1/admin/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, admin_credentials)}"}


def _tool_payload(code: str = "my_custom_tool", **over) -> dict:
    base = {
        "code": code,
        "name": "Mi tool",
        "description": "Hace algo útil",
        "parameters_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "target_service": "crm.person.find",
        "requires_confirmation": False,
    }
    base.update(over)
    return base


async def _create_tool(client: AsyncClient, headers: dict, **over) -> dict:
    r = await client.post(f"{PREFIX}/tools", json=_tool_payload(**over), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_create_tool(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    data = await _create_tool(client, headers, code="tool_create")
    assert data["code"] == "tool_create"
    assert data["target_service"] == "crm.person.find"
    assert data["is_registered"] is False  # code no está en TOOL_REGISTRY
    assert data["active"] is True
    assert data["parameters_schema"]["type"] == "object"


async def test_create_tool_registered_flag(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Una tool cuyo code SÍ está en el TOOL_REGISTRY se marca is_registered=True. El seed ya crea
    estas filas, así que en vez de duplicar el code (409) leemos la fila seedeada vía /list."""
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/tools/list",
        json={"pagination": {"skip": 0, "limit": 100}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    registered = [t for t in items if t["is_registered"]]
    # el seed inscribe tools cuyo code está registrado (crm/catalog/scheduling/marketing/clock)
    assert registered, "se esperaba al menos una tool seedeada con is_registered=True"


async def test_create_tool_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_tool(client, headers, code="tool_dup")
    r = await client.post(f"{PREFIX}/tools", json=_tool_payload(code="tool_dup"), headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "BOT_TOOL_CODE_TAKEN"


async def test_create_tool_invalid_code_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(f"{PREFIX}/tools", json=_tool_payload(code="BAD CODE"), headers=headers)
    assert r.status_code == 422, r.text


async def test_get_tool(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_tool(client, headers, code="tool_get")
    r = await client.get(f"{PREFIX}/tools/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]
    assert "parameters_schema" in r.json()["data"]


async def test_get_tool_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/tools/nope", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_TOOL_NOT_FOUND"


async def test_list_tools_paginated(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_tool(client, headers, code="tool_list_a")
    r = await client.post(
        f"{PREFIX}/tools/list",
        json={"pagination": {"skip": 0, "limit": 100}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    codes = {i["code"] for i in r.json()["data"]["items"]}
    assert "tool_list_a" in codes


async def test_list_active_tools(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_tool(client, headers, code="tool_active")
    r = await client.get(f"{PREFIX}/tools/active", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()  # lista cruda
    assert isinstance(body, list)
    assert any(t["code"] == "tool_active" for t in body)


async def test_update_tool(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_tool(client, headers, code="tool_upd")
    r = await client.put(
        f"{PREFIX}/tools/{created['id']}",
        json={"name": "Nombre nuevo", "requires_confirmation": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Nombre nuevo"
    assert data["requires_confirmation"] is True
    assert data["code"] == "tool_upd"  # code no editable, intacto


async def test_update_tool_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(f"{PREFIX}/tools/nope", json={"name": "x"}, headers=headers)
    assert r.status_code == 404, r.text


async def test_update_tool_deactivate(client: AsyncClient, admin_credentials: dict) -> None:
    """active=False SÍ cambia (no se descarta como None)."""
    headers = await _headers(client, admin_credentials)
    created = await _create_tool(client, headers, code="tool_deact")
    r = await client.put(
        f"{PREFIX}/tools/{created['id']}", json={"active": False}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["active"] is False


async def test_delete_tool(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_tool(client, headers, code="tool_del")
    r = await client.delete(f"{PREFIX}/tools/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    r2 = await client.get(f"{PREFIX}/tools/{created['id']}", headers=headers)
    assert r2.status_code == 404


async def test_delete_tool_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/tools/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_requires_auth(client: AsyncClient) -> None:
    r = await client.post(f"{PREFIX}/tools/list", json={"pagination": {"skip": 0, "limit": 10}})
    assert r.status_code in (401, 403), r.text
