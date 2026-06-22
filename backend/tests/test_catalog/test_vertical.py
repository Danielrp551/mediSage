"""
Tests de integración para el recurso Vertical del módulo catalog.

Cubren el service `app.modules.catalog.services.vertical` end-to-end vía la
API pública: happy paths (create/get/list/active/update/delete) + casos de
borde (404, 409 por code duplicado, 409 por hijos activos, 422 de validación).
"""

from __future__ import annotations

from httpx import AsyncClient

PREFIX = "/api/v1/catalog/verticals"
SVC_PREFIX = "/api/v1/catalog/services"


async def _token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post("/api/v1/admin/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, admin_credentials)}"}


def _vertical_payload(**overrides) -> dict:
    base = {
        "code": "dermatologia",
        "name": "Dermatología",
        "description": "Servicios dermatológicos",
        "color": "#AABBCC",
        "icon": "skin",
        "display_order": 1,
    }
    base.update(overrides)
    return base


async def _create_vertical(client: AsyncClient, headers: dict, **overrides) -> dict:
    r = await client.post(f"{PREFIX}", json=_vertical_payload(**overrides), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_create_vertical_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(f"{PREFIX}", json=_vertical_payload(), headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["code"] == "dermatologia"
    assert data["name"] == "Dermatología"
    assert data["color"] == "#AABBCC"  # normalizado a mayúsculas
    assert data["active"] is True
    assert data["services_count"] == 0
    assert data["products_count"] == 0
    assert data["created_by_user"]["email"] == admin_credentials["email"]


async def test_create_vertical_minimal(client: AsyncClient, admin_credentials: dict) -> None:
    """Solo code + name (los demás campos son opcionales con default)."""
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}", json={"code": "odontologia", "name": "Odontología"}, headers=headers
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["display_order"] == 0
    assert data["color"] is None


async def test_create_vertical_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_vertical(client, headers)
    r = await client.post(f"{PREFIX}", json=_vertical_payload(), headers=headers)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["success"] is False
    assert body["code"] == "VERTICAL_CODE_TAKEN"


async def test_create_vertical_invalid_code_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}", json={"code": "Bad Code!", "name": "X"}, headers=headers
    )
    assert r.status_code == 422, r.text


async def test_create_vertical_invalid_color_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}", json=_vertical_payload(color="red"), headers=headers
    )
    assert r.status_code == 422, r.text


async def test_get_vertical_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_vertical(client, headers)
    r = await client.get(f"{PREFIX}/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == created["id"]
    assert data["code"] == "dermatologia"


async def test_get_vertical_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/nonexistent-id", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["success"] is False


async def test_list_active_verticals(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_vertical(client, headers)
    r = await client.get(f"{PREFIX}/active", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()  # lista cruda (sin envelope)
    assert isinstance(items, list)
    assert created["id"] in [v["id"] for v in items]


async def test_list_paginated_verticals(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_vertical(client, headers, code="vert_a", name="Vert A")
    await _create_vertical(client, headers, code="vert_b", name="Vert B")
    r = await client.post(
        f"{PREFIX}/list", json={"pagination": {"skip": 0, "limit": 10}}, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


async def test_list_paginated_with_filter(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_vertical(client, headers, code="filterme", name="Filtrable")
    await _create_vertical(client, headers, code="other", name="Otra")
    body = {
        "pagination": {"skip": 0, "limit": 10},
        "filters": {
            "filters": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "code", "operator": "eq", "value": "filterme"}
                    ],
                }
            ]
        },
    }
    r = await client.post(f"{PREFIX}/list", json=body, headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["code"] == "filterme"


async def test_update_vertical_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_vertical(client, headers)
    r = await client.put(
        f"{PREFIX}/{created['id']}",
        json={"name": "Dermatología Renovada", "display_order": 5, "active": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Dermatología Renovada"
    assert data["display_order"] == 5
    assert data["active"] is False
    assert data["code"] == "dermatologia"  # code inmutable


async def test_update_vertical_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(
        f"{PREFIX}/nonexistent", json={"name": "X"}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_update_vertical_invalid_color_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_vertical(client, headers)
    r = await client.put(
        f"{PREFIX}/{created['id']}", json={"color": "notahex"}, headers=headers
    )
    assert r.status_code == 422, r.text


async def test_delete_vertical_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_vertical(client, headers)
    r = await client.delete(f"{PREFIX}/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # ya no aparece
    g = await client.get(f"{PREFIX}/{created['id']}", headers=headers)
    assert g.status_code == 404


async def test_delete_vertical_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/nonexistent", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_vertical_with_active_children_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """No se puede borrar una vertical con un servicio activo colgando."""
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    svc = await client.post(
        f"{SVC_PREFIX}",
        json={
            "vertical_id": vertical["id"],
            "code": "limpieza",
            "name": "Limpieza facial",
        },
        headers=headers,
    )
    assert svc.status_code == 201, svc.text
    r = await client.delete(f"{PREFIX}/{vertical['id']}", headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "VERTICAL_HAS_ACTIVE_CHILDREN"


async def test_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{PREFIX}/active")
    assert r.status_code == 401
