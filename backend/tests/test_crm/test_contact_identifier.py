"""Tests del CRUD anidado de PersonContactIdentifier (/persons/{id}/identifiers)."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_crm.conftest import CRM, auth_headers, create_person


async def _add(client, headers, person_id, **body):
    r = await client.post(
        f"{CRM}/persons/{person_id}/identifiers", json=body, headers=headers
    )
    return r


async def test_list_identifiers_empty(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.get(f"{CRM}/persons/{person['id']}/identifiers", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_add_identifier(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await _add(
        client, headers, person["id"], channel_type="whatsapp", identifier="+51900", is_primary=True
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["channel_type"] == "whatsapp"
    assert data["is_primary"] is True


async def test_add_identifier_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await _add(client, headers, "nope", channel_type="email", identifier="a@b.com")
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


async def test_add_identifier_duplicate_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    p1 = await create_person(client, headers, first_name="A")
    p2 = await create_person(client, headers, first_name="B")
    r1 = await _add(client, headers, p1["id"], channel_type="email", identifier="dup@x.com")
    assert r1.status_code == 201
    r2 = await _add(client, headers, p2["id"], channel_type="email", identifier="dup@x.com")
    assert r2.status_code == 409, r2.text
    assert r2.json()["code"] == "IDENTIFIER_TAKEN"


async def test_add_second_primary_unmarks_previous(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r1 = await _add(
        client, headers, person["id"], channel_type="whatsapp", identifier="+51111", is_primary=True
    )
    first_id = r1.json()["data"]["id"]
    await _add(
        client, headers, person["id"], channel_type="whatsapp", identifier="+51222", is_primary=True
    )
    r = await client.get(f"{CRM}/persons/{person['id']}/identifiers", headers=headers)
    by_id = {i["id"]: i for i in r.json()["data"]}
    assert by_id[first_id]["is_primary"] is False


async def test_update_identifier(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r1 = await _add(client, headers, person["id"], channel_type="email", identifier="old@x.com")
    ident_id = r1.json()["data"]["id"]
    r = await client.put(
        f"{CRM}/persons/{person['id']}/identifiers/{ident_id}",
        json={"identifier": "new@x.com", "verified": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["identifier"] == "new@x.com"
    assert data["verified"] is True


async def test_update_identifier_to_taken_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _add(client, headers, person["id"], channel_type="email", identifier="taken@x.com")
    r1 = await _add(client, headers, person["id"], channel_type="email", identifier="free@x.com")
    ident_id = r1.json()["data"]["id"]
    r = await client.put(
        f"{CRM}/persons/{person['id']}/identifiers/{ident_id}",
        json={"identifier": "taken@x.com"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDENTIFIER_TAKEN"


async def test_update_identifier_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.put(
        f"{CRM}/persons/{person['id']}/identifiers/nope",
        json={"verified": True},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "IDENTIFIER_NOT_FOUND"


async def test_update_identifier_promote_primary(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r1 = await _add(
        client, headers, person["id"], channel_type="phone", identifier="+5101", is_primary=True
    )
    first_id = r1.json()["data"]["id"]
    r2 = await _add(client, headers, person["id"], channel_type="phone", identifier="+5102")
    second_id = r2.json()["data"]["id"]
    r = await client.put(
        f"{CRM}/persons/{person['id']}/identifiers/{second_id}",
        json={"is_primary": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    listing = await client.get(
        f"{CRM}/persons/{person['id']}/identifiers", headers=headers
    )
    by_id = {i["id"]: i for i in listing.json()["data"]}
    assert by_id[first_id]["is_primary"] is False
    assert by_id[second_id]["is_primary"] is True


async def test_delete_identifier(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r1 = await _add(client, headers, person["id"], channel_type="email", identifier="del@x.com")
    ident_id = r1.json()["data"]["id"]
    r = await client.delete(
        f"{CRM}/persons/{person['id']}/identifiers/{ident_id}", headers=headers
    )
    assert r.status_code == 204, r.text
    listing = await client.get(
        f"{CRM}/persons/{person['id']}/identifiers", headers=headers
    )
    assert listing.json()["data"] == []


async def test_delete_identifier_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.delete(
        f"{CRM}/persons/{person['id']}/identifiers/nope", headers=headers
    )
    assert r.status_code == 404, r.text
