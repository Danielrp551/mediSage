"""
Tests de integración del service `office` (consultorios).

Cubre create/get/list/active/update/delete + casos de borde: branch inexistente
(404 BRANCH_NOT_FOUND), código duplicado por sede (409 OFFICE_CODE_TAKEN),
vertical inexistente (400), filtros del /active por branch y vertical, y el
reemplazo M:N de verticales en update.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_clinic.conftest import (
    CLINIC,
    auth_headers,
    create_branch,
    create_office,
    create_vertical,
    office_payload,
)


async def test_create_office_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload(branch["id"], floor="2", room_number="201"),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["branch_id"] == branch["id"]
    assert data["branch_name"] == branch["name"]
    assert data["floor"] == "2"
    assert data["active"] is True
    assert data["verticals"] == []
    assert data["branch"]["id"] == branch["id"]


async def test_create_office_with_verticals(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    v1 = await create_vertical(client, headers, code="estetica")
    v2 = await create_vertical(client, headers, code="dermatologia")
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload(branch["id"], vertical_ids=[v1["id"], v2["id"]]),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["verticals_count"] == 2
    returned = {v["id"] for v in data["verticals"]}
    assert returned == {v1["id"], v2["id"]}


async def test_create_office_branch_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload("ghost-branch"),
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BRANCH_NOT_FOUND"


async def test_create_office_duplicate_code_409(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    await create_office(client, headers, branch["id"], code="c-dup")
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload(branch["id"], code="c-dup"),
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "OFFICE_CODE_TAKEN"


async def test_create_office_same_code_other_branch_ok(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    b1 = await create_branch(client, headers, code="sede_uno")
    b2 = await create_branch(client, headers, code="sede_dos")
    await create_office(client, headers, b1["id"], code="c-01")
    # Same office code is allowed under a different branch (uniqueness is per-branch).
    r = await client.post(
        f"{CLINIC}/offices", json=office_payload(b2["id"], code="c-01"), headers=headers
    )
    assert r.status_code == 201, r.text


async def test_create_office_unknown_vertical_400(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload(branch["id"], vertical_ids=["ghost-vertical"]),
        headers=headers,
    )
    assert r.status_code == 400, r.text


async def test_create_office_duplicate_vertical_ids_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    v = await create_vertical(client, headers)
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload(branch["id"], vertical_ids=[v["id"], v["id"]]),
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_office_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    office = await create_office(client, headers, branch["id"])
    r = await client.get(f"{CLINIC}/offices/{office['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == office["id"]


async def test_get_office_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CLINIC}/offices/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_offices_paginated(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    await create_office(client, headers, branch["id"], code="c-01")
    await create_office(client, headers, branch["id"], code="c-02")
    r = await client.post(
        f"{CLINIC}/offices/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 2
    # branch_name denormalized into the row.
    assert all(item["branch_name"] == branch["name"] for item in data["items"])


async def test_list_active_offices_filter_by_branch(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    b1 = await create_branch(client, headers, code="sede_one")
    b2 = await create_branch(client, headers, code="sede_two")
    await create_office(client, headers, b1["id"], code="o-a")
    await create_office(client, headers, b2["id"], code="o-b")
    r = await client.get(
        f"{CLINIC}/offices/active", params={"branch_id": b1["id"]}, headers=headers
    )
    assert r.status_code == 200, r.text
    options = r.json()
    assert isinstance(options, list)
    assert all(o["branch_id"] == b1["id"] for o in options)
    assert any(o["code"] == "o-a" for o in options)


async def test_list_active_offices_filter_by_vertical(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    v = await create_vertical(client, headers)
    await create_office(client, headers, branch["id"], code="with-v", vertical_ids=[v["id"]])
    await create_office(client, headers, branch["id"], code="no-v")
    r = await client.get(
        f"{CLINIC}/offices/active", params={"vertical_id": v["id"]}, headers=headers
    )
    assert r.status_code == 200, r.text
    options = r.json()
    codes = {o["code"] for o in options}
    assert "with-v" in codes
    assert "no-v" not in codes


async def test_update_office_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    office = await create_office(client, headers, branch["id"])
    r = await client.put(
        f"{CLINIC}/offices/{office['id']}",
        json={"name": "Consultorio Renombrado", "floor": "3"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Consultorio Renombrado"
    assert data["floor"] == "3"


async def test_update_office_replace_verticals(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    v1 = await create_vertical(client, headers, code="estetica")
    v2 = await create_vertical(client, headers, code="dermatologia")
    office = await create_office(client, headers, branch["id"], vertical_ids=[v1["id"]])
    # Replace the M:N set with just v2.
    r = await client.put(
        f"{CLINIC}/offices/{office['id']}",
        json={"vertical_ids": [v2["id"]]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert {v["id"] for v in data["verticals"]} == {v2["id"]}


async def test_update_office_clear_verticals(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    v = await create_vertical(client, headers)
    office = await create_office(client, headers, branch["id"], vertical_ids=[v["id"]])
    r = await client.put(
        f"{CLINIC}/offices/{office['id']}",
        json={"vertical_ids": []},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verticals"] == []


async def test_update_office_unknown_vertical_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    office = await create_office(client, headers, branch["id"])
    r = await client.put(
        f"{CLINIC}/offices/{office['id']}",
        json={"vertical_ids": ["ghost"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text


async def test_update_office_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{CLINIC}/offices/nope", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_office_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    office = await create_office(client, headers, branch["id"])
    r = await client.delete(f"{CLINIC}/offices/{office['id']}", headers=headers)
    assert r.status_code == 204, r.text
    g = await client.get(f"{CLINIC}/offices/{office['id']}", headers=headers)
    assert g.status_code == 404


async def test_delete_office_then_branch_ok(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    branch = await create_branch(client, headers)
    office = await create_office(client, headers, branch["id"])
    # Deleting the office unblocks the branch delete guard.
    await client.delete(f"{CLINIC}/offices/{office['id']}", headers=headers)
    r = await client.delete(f"{CLINIC}/branches/{branch['id']}", headers=headers)
    assert r.status_code == 204, r.text


async def test_delete_office_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{CLINIC}/offices/nope", headers=headers)
    assert r.status_code == 404, r.text
