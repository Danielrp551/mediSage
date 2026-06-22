"""
Tests de integración del service `branch` (sedes).

Cubre happy paths (create/get/list/active/update/delete) + casos de borde:
404 en recursos inexistentes, 409 por código duplicado, 409 al eliminar una
sede con consultorios activos, 422 por validación de slug/país/timezone.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_clinic.conftest import (
    CLINIC,
    auth_headers,
    branch_payload,
    create_branch,
    create_office,
)


async def test_create_branch_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CLINIC}/branches", json=branch_payload(), headers=headers
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"] == "sede_lima"
    assert data["name"] == "Sede Lima Centro"
    assert data["active"] is True
    assert data["offices_count"] == 0
    assert data["created_by_user"]["email"] == admin_credentials["email"]


async def test_create_branch_normalizes_country(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    # lowercase 2-letter country gets upper-cased by the validator.
    data = await create_branch(client, headers, country="mx")
    assert data["country"] == "MX"


async def test_create_branch_duplicate_code_409(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_branch(client, headers, code="sede_dup")
    r = await client.post(
        f"{CLINIC}/branches", json=branch_payload("sede_dup"), headers=headers
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["success"] is False
    assert body["code"] == "BRANCH_CODE_TAKEN"


async def test_create_branch_invalid_code_422(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    # Uppercase + leading digit are not a valid slug.
    r = await client.post(
        f"{CLINIC}/branches", json=branch_payload("1Bad"), headers=headers
    )
    assert r.status_code == 422, r.text


async def test_create_branch_invalid_country_422(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CLINIC}/branches", json=branch_payload(country="PER"), headers=headers
    )
    assert r.status_code == 422, r.text


async def test_create_branch_invalid_timezone_422(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CLINIC}/branches", json=branch_payload(timezone="NotATimezone"), headers=headers
    )
    assert r.status_code == 422, r.text


async def test_get_branch_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_branch(client, headers)
    r = await client.get(f"{CLINIC}/branches/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]


async def test_get_branch_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CLINIC}/branches/does-not-exist", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["success"] is False


async def test_list_branches_paginated(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_branch(client, headers, code="sede_a")
    await create_branch(client, headers, code="sede_b")
    r = await client.post(
        f"{CLINIC}/branches/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 2
    codes = {item["code"] for item in data["items"]}
    assert {"sede_a", "sede_b"} <= codes


async def test_list_branches_filtered(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_branch(client, headers, code="sede_filter")
    await create_branch(client, headers, code="otra_sede")
    body = {
        "pagination": {"skip": 0, "limit": 10},
        "filters": {
            "filters": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "code", "operator": "eq", "value": "sede_filter"}
                    ],
                }
            ]
        },
    }
    r = await client.post(f"{CLINIC}/branches/list", json=body, headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["code"] == "sede_filter"


async def test_list_active_branches(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_branch(client, headers, code="sede_active")
    r = await client.get(f"{CLINIC}/branches/active", headers=headers)
    assert r.status_code == 200, r.text
    # /active returns a raw list (no envelope).
    options = r.json()
    assert isinstance(options, list)
    assert any(o["code"] == "sede_active" for o in options)


async def test_update_branch_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_branch(client, headers)
    r = await client.put(
        f"{CLINIC}/branches/{created['id']}",
        json={"name": "Sede Renombrada", "city": "Arequipa"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Sede Renombrada"
    assert data["city"] == "Arequipa"
    # code is immutable, unchanged.
    assert data["code"] == created["code"]


async def test_update_branch_disable(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_branch(client, headers)
    r = await client.put(
        f"{CLINIC}/branches/{created['id']}",
        json={"active": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["active"] is False


async def test_update_branch_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(
        f"{CLINIC}/branches/nope", json={"name": "X"}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_update_branch_invalid_timezone_422(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_branch(client, headers)
    r = await client.put(
        f"{CLINIC}/branches/{created['id']}",
        json={"timezone": "bogus"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_delete_branch_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_branch(client, headers)
    r = await client.delete(f"{CLINIC}/branches/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # Soft-deleted: subsequent get is 404.
    g = await client.get(f"{CLINIC}/branches/{created['id']}", headers=headers)
    assert g.status_code == 404


async def test_delete_branch_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{CLINIC}/branches/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_branch_with_active_offices_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    await create_office(client, headers, branch["id"])
    r = await client.delete(f"{CLINIC}/branches/{branch['id']}", headers=headers)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["success"] is False
    assert body["code"] == "BRANCH_HAS_ACTIVE_CHILDREN"


async def test_branch_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{CLINIC}/branches/active")
    assert r.status_code == 401
