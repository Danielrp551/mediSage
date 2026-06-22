"""
Tests de integración para el recurso Service del módulo catalog.

Cubren el service `app.modules.catalog.services.service` end-to-end: crea la
vertical padre vía API, luego ejercita create/get/list/active/update/delete +
casos de borde (404 vertical, 404 service, 409 code duplicado por vertical,
409 hijos activos, scoping por vertical_id en /active).
"""

from __future__ import annotations

from httpx import AsyncClient

VERT_PREFIX = "/api/v1/catalog/verticals"
PREFIX = "/api/v1/catalog/services"
PROD_PREFIX = "/api/v1/catalog/products"


async def _token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post("/api/v1/admin/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, admin_credentials)}"}


async def _create_vertical(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {"code": "dermatologia", "name": "Dermatología"}
    payload.update(overrides)
    r = await client.post(f"{VERT_PREFIX}", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _create_service(
    client: AsyncClient, headers: dict, vertical_id: str, **overrides
) -> dict:
    payload = {
        "vertical_id": vertical_id,
        "code": "limpieza_facial",
        "name": "Limpieza facial",
        "description": "Tratamiento de limpieza",
        "display_order": 1,
    }
    payload.update(overrides)
    r = await client.post(f"{PREFIX}", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_create_service_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    r = await client.post(
        f"{PREFIX}",
        json={
            "vertical_id": vertical["id"],
            "code": "limpieza_facial",
            "name": "Limpieza facial",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"] == "limpieza_facial"
    assert data["vertical_id"] == vertical["id"]
    assert data["vertical_name"] == "Dermatología"  # denormalizado
    assert data["vertical"]["id"] == vertical["id"]
    assert data["products_count"] == 0
    assert data["active"] is True


async def test_create_service_vertical_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}",
        json={"vertical_id": "nope", "code": "abc_def", "name": "X"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "VERTICAL_NOT_FOUND"


async def test_create_service_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    await _create_service(client, headers, vertical["id"])
    r = await client.post(
        f"{PREFIX}",
        json={
            "vertical_id": vertical["id"],
            "code": "limpieza_facial",
            "name": "Otra",
        },
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "SERVICE_CODE_TAKEN"


async def test_create_service_same_code_different_vertical_ok(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """El code es único POR vertical, no global."""
    headers = await _headers(client, admin_credentials)
    v1 = await _create_vertical(client, headers, code="vert_uno", name="Uno")
    v2 = await _create_vertical(client, headers, code="vert_dos", name="Dos")
    await _create_service(client, headers, v1["id"], code="comun")
    r = await client.post(
        f"{PREFIX}",
        json={"vertical_id": v2["id"], "code": "comun", "name": "Comun en V2"},
        headers=headers,
    )
    assert r.status_code == 201, r.text


async def test_create_service_invalid_code_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    r = await client.post(
        f"{PREFIX}",
        json={"vertical_id": vertical["id"], "code": "BAD", "name": "X"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_service_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    created = await _create_service(client, headers, vertical["id"])
    r = await client.get(f"{PREFIX}/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == created["id"]
    assert data["vertical"]["code"] == "dermatologia"


async def test_get_service_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_active_services_scoped(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    v1 = await _create_vertical(client, headers, code="vert_uno", name="Uno")
    v2 = await _create_vertical(client, headers, code="vert_dos", name="Dos")
    s1 = await _create_service(client, headers, v1["id"], code="serv_uno")
    await _create_service(client, headers, v2["id"], code="serv_dos")

    # sin scope: ambos
    r_all = await client.get(f"{PREFIX}/active", headers=headers)
    assert r_all.status_code == 200, r_all.text
    assert len(r_all.json()) >= 2

    # con scope a v1: solo s1
    r_scoped = await client.get(
        f"{PREFIX}/active", params={"vertical_id": v1["id"]}, headers=headers
    )
    assert r_scoped.status_code == 200, r_scoped.text
    items = r_scoped.json()
    ids = [s["id"] for s in items]
    assert s1["id"] in ids
    assert all(s["vertical_id"] == v1["id"] for s in items)


async def test_list_paginated_services(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    await _create_service(client, headers, vertical["id"], code="serv_a")
    await _create_service(client, headers, vertical["id"], code="serv_b")
    r = await client.post(
        f"{PREFIX}/list", json={"pagination": {"skip": 0, "limit": 10}}, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 2
    # vertical_name denormalizado presente en el listado
    assert all(item["vertical_name"] == "Dermatología" for item in data["items"])


async def test_update_service_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    created = await _create_service(client, headers, vertical["id"])
    r = await client.put(
        f"{PREFIX}/{created['id']}",
        json={"name": "Limpieza Premium", "active": False, "display_order": 9},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Limpieza Premium"
    assert data["active"] is False
    assert data["display_order"] == 9
    assert data["code"] == "limpieza_facial"  # inmutable


async def test_update_service_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(f"{PREFIX}/nope", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_service_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    created = await _create_service(client, headers, vertical["id"])
    r = await client.delete(f"{PREFIX}/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    g = await client.get(f"{PREFIX}/{created['id']}", headers=headers)
    assert g.status_code == 404


async def test_delete_service_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_service_with_active_products_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """No se puede borrar un servicio con un producto activo colgando."""
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    service = await _create_service(client, headers, vertical["id"])
    prod = await client.post(
        f"{PROD_PREFIX}",
        json={
            "service_id": service["id"],
            "code": "facial_basico",
            "name": "Facial básico",
            "base_price": "100.00",
        },
        headers=headers,
    )
    assert prod.status_code == 201, prod.text
    r = await client.delete(f"{PREFIX}/{service['id']}", headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "SERVICE_HAS_ACTIVE_CHILDREN"
