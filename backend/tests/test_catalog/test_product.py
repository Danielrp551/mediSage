"""
Tests de integración para el recurso Product del módulo catalog.

Cubren el service `app.modules.catalog.services.product` end-to-end: crea
vertical -> service -> product vía API, luego ejercita create/get/list/active/
update/delete + casos de borde (404 service, 404 product, 409 code duplicado
por service, 422 cross-field duración, scoping por service_id, soft-delete sin
guard por ser hoja del árbol).
"""

from __future__ import annotations

from httpx import AsyncClient

VERT_PREFIX = "/api/v1/catalog/verticals"
SVC_PREFIX = "/api/v1/catalog/services"
PREFIX = "/api/v1/catalog/products"


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


async def _create_service(client: AsyncClient, headers: dict, vertical_id: str, **overrides) -> dict:
    payload = {
        "vertical_id": vertical_id,
        "code": "limpieza_facial",
        "name": "Limpieza facial",
    }
    payload.update(overrides)
    r = await client.post(f"{SVC_PREFIX}", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _scaffold(client: AsyncClient, headers: dict) -> dict:
    """Crea vertical + service y devuelve el service (con vertical embebido)."""
    vertical = await _create_vertical(client, headers)
    return await _create_service(client, headers, vertical["id"])


def _product_payload(service_id: str, **overrides) -> dict:
    base = {
        "service_id": service_id,
        "code": "facial_basico",
        "name": "Facial básico",
        "description": "Sesión de limpieza facial",
        "base_price": "150.50",
        "currency": "PEN",
        "duration_min": 60,
        "requires_appointment": True,
        "is_package": False,
        "min_hours_to_cancel": 24,
    }
    base.update(overrides)
    return base


async def _create_product(client: AsyncClient, headers: dict, service_id: str, **overrides) -> dict:
    r = await client.post(f"{PREFIX}", json=_product_payload(service_id, **overrides), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_create_product_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    r = await client.post(
        f"{PREFIX}", json=_product_payload(service["id"]), headers=headers
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"] == "facial_basico"
    assert data["service_id"] == service["id"]
    assert data["service_name"] == "Limpieza facial"  # denormalizado
    assert data["vertical_id"] == service["vertical_id"]
    assert data["vertical_name"] == "Dermatología"  # denormalizado del abuelo
    assert data["base_price"] == "150.50"
    assert data["currency"] == "PEN"
    assert data["duration_min"] == 60
    assert data["service"]["id"] == service["id"]
    assert data["vertical"]["id"] == service["vertical_id"]


async def test_create_product_minimal(client: AsyncClient, admin_credentials: dict) -> None:
    """Solo los campos obligatorios; defaults aplican."""
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    r = await client.post(
        f"{PREFIX}",
        json={
            "service_id": service["id"],
            "code": "simple_prod",
            "name": "Producto simple",
            "base_price": "0",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["currency"] == "PEN"
    assert data["requires_appointment"] is True
    assert data["is_package"] is False
    assert data["duration_min"] is None


async def test_create_product_service_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}",
        json={
            "service_id": "nope",
            "code": "abc_def",
            "name": "X",
            "base_price": "10",
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "SERVICE_NOT_FOUND"


async def test_create_product_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    await _create_product(client, headers, service["id"])
    r = await client.post(
        f"{PREFIX}", json=_product_payload(service["id"]), headers=headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PRODUCT_CODE_TAKEN"


async def test_create_product_cross_field_duration_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """requires_appointment + min_hours_to_cancel set + duration NULL -> 422."""
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    r = await client.post(
        f"{PREFIX}",
        json=_product_payload(
            service["id"], duration_min=None, min_hours_to_cancel=12
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_create_product_invalid_currency_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    r = await client.post(
        f"{PREFIX}",
        json=_product_payload(service["id"], currency="peso"),
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_create_product_negative_price_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    r = await client.post(
        f"{PREFIX}",
        json=_product_payload(service["id"], base_price="-5"),
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_product_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    created = await _create_product(client, headers, service["id"])
    r = await client.get(f"{PREFIX}/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == created["id"]
    assert data["service"]["code"] == "limpieza_facial"
    assert data["vertical"]["code"] == "dermatologia"


async def test_get_product_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_active_products_scoped(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    vertical = await _create_vertical(client, headers)
    s1 = await _create_service(client, headers, vertical["id"], code="serv_uno")
    s2 = await _create_service(client, headers, vertical["id"], code="serv_dos")
    p1 = await _create_product(client, headers, s1["id"], code="prod_uno")
    await _create_product(client, headers, s2["id"], code="prod_dos")

    r_all = await client.get(f"{PREFIX}/active", headers=headers)
    assert r_all.status_code == 200, r_all.text
    assert len(r_all.json()) >= 2

    r_scoped = await client.get(
        f"{PREFIX}/active", params={"service_id": s1["id"]}, headers=headers
    )
    assert r_scoped.status_code == 200, r_scoped.text
    items = r_scoped.json()
    assert p1["id"] in [p["id"] for p in items]
    assert all(p["service_id"] == s1["id"] for p in items)
    # ProductOption lleva price + duration para booking
    assert all("base_price" in p and "duration_min" in p for p in items)


async def test_list_paginated_products(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    await _create_product(client, headers, service["id"], code="prod_a")
    await _create_product(client, headers, service["id"], code="prod_b")
    r = await client.post(
        f"{PREFIX}/list", json={"pagination": {"skip": 0, "limit": 10}}, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 2
    assert all(item["service_name"] == "Limpieza facial" for item in data["items"])


async def test_update_product_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    created = await _create_product(client, headers, service["id"])
    r = await client.put(
        f"{PREFIX}/{created['id']}",
        json={
            "name": "Facial Premium",
            "base_price": "200.00",
            "duration_min": 90,
            "active": False,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Facial Premium"
    assert data["base_price"] == "200.00"
    assert data["duration_min"] == 90
    assert data["active"] is False
    assert data["code"] == "facial_basico"  # inmutable


async def test_update_product_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(f"{PREFIX}/nope", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text


async def test_update_product_invalid_currency_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    created = await _create_product(client, headers, service["id"])
    r = await client.put(
        f"{PREFIX}/{created['id']}", json={"currency": "lowercase"}, headers=headers
    )
    assert r.status_code == 422, r.text


async def test_delete_product_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    service = await _scaffold(client, headers)
    created = await _create_product(client, headers, service["id"])
    r = await client.delete(f"{PREFIX}/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    g = await client.get(f"{PREFIX}/{created['id']}", headers=headers)
    assert g.status_code == 404


async def test_delete_product_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/nope", headers=headers)
    assert r.status_code == 404, r.text
