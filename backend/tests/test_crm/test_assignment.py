"""Tests de asignación de owner (LeadAssignment) + advisors + bandeja del asesor."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_crm.conftest import CRM, auth_headers, create_advisor, create_person


async def test_list_advisors_active(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    advisor_id = await create_advisor(client, headers)
    r = await client.get(f"{CRM}/advisors/active", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert any(a["id"] == advisor_id for a in rows)


async def test_get_assignment_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.get(f"{CRM}/persons/{person['id']}/assignment", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "ASSIGNMENT_NOT_FOUND"


async def test_get_assignment_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CRM}/persons/nope/assignment", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


async def test_reassign_manual(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    advisor_id = await create_advisor(client, headers)
    person = await create_person(client, headers)
    r = await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": advisor_id, "reason": "Manual"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["advisor"]["id"] == advisor_id
    # GET ahora devuelve el owner.
    g = await client.get(f"{CRM}/persons/{person['id']}/assignment", headers=headers)
    assert g.status_code == 200
    assert g.json()["data"]["advisor"]["id"] == advisor_id


async def test_reassign_idempotent_same_advisor(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    advisor_id = await create_advisor(client, headers)
    person = await create_person(client, headers)
    await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": advisor_id},
        headers=headers,
    )
    r = await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": advisor_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["advisor"]["id"] == advisor_id


async def test_reassign_rotates_owner(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    a1 = await create_advisor(client, headers, email="a1@example.com", first_name="Uno")
    a2 = await create_advisor(client, headers, email="a2@example.com", first_name="Dos")
    person = await create_person(client, headers)
    await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": a1},
        headers=headers,
    )
    r = await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": a2},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["advisor"]["id"] == a2


async def test_reassign_advisor_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": "ghost"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "ADVISOR_NOT_FOUND"


async def test_reassign_advisor_not_asesor(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """El admin (sin rol ASESOR) no puede ser asignado como owner."""
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    me = await client.get("/api/v1/admin/auth/me", headers=headers)
    admin_id = me.json()["id"]
    r = await client.put(
        f"{CRM}/persons/{person['id']}/assignment",
        json={"advisor_user_id": admin_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "ADVISOR_NOT_ASESOR"


async def test_auto_assign_round_robin(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    advisor_id = await create_advisor(client, headers)
    person = await create_person(client, headers)
    r = await client.post(
        f"{CRM}/persons/{person['id']}/assignment/auto", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["advisor"]["id"] == advisor_id


async def test_auto_assign_idempotent(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    advisor_id = await create_advisor(client, headers)
    person = await create_person(client, headers)
    await client.post(f"{CRM}/persons/{person['id']}/assignment/auto", headers=headers)
    r = await client.post(
        f"{CRM}/persons/{person['id']}/assignment/auto", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["advisor"]["id"] == advisor_id


async def test_auto_assign_no_advisor_available(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.post(
        f"{CRM}/persons/{person['id']}/assignment/auto", headers=headers
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "NO_ADVISOR_AVAILABLE"


async def test_list_my_leads(client: AsyncClient, admin_credentials: dict) -> None:
    """La bandeja del asesor logueado. El admin tiene MY_LEADS_READ; no es ASESOR,
    así que su bandeja estará vacía pero el endpoint responde 200."""
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CRM}/me/leads/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "items" in body
    assert "total" in body
