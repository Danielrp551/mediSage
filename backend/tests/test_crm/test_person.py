"""Tests de integración del CRUD de Person + identifiers inline + search/active."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_crm.conftest import CRM, auth_headers, create_person


async def test_create_person_minimal(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    data = await create_person(client, headers, first_name="Ana", last_name="Perez")
    assert data["full_name"] == "Ana Perez"
    assert data["active"] is True
    assert data["identifiers"] == []
    # Audit hidratado.
    assert data["created_by_user"]["email"] == admin_credentials["email"]


async def test_create_person_with_identifiers(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    data = await create_person(
        client,
        headers,
        first_name="Luis",
        last_name="Gomez",
        second_last_name="Diaz",
        document_type="DNI",
        document_number="12345678",
        identifiers=[
            {"channel_type": "whatsapp", "identifier": "+51999111222", "is_primary": True},
            {"channel_type": "email", "identifier": "luis@example.com"},
        ],
    )
    assert data["full_name"] == "Luis Gomez Diaz"
    assert len(data["identifiers"]) == 2
    assert data["primary_identifier"]["identifier"] == "+51999111222"


async def test_create_person_duplicate_identifier_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_person(
        client,
        headers,
        identifiers=[{"channel_type": "whatsapp", "identifier": "+51900000000"}],
    )
    r = await client.post(
        f"{CRM}/persons",
        json={
            "first_name": "Otro",
            "last_name": "Lead",
            "identifiers": [{"channel_type": "whatsapp", "identifier": "+51900000000"}],
        },
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDENTIFIER_TAKEN"


async def test_create_person_duplicate_inline_identifier_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CRM}/persons",
        json={
            "first_name": "Dup",
            "last_name": "Inline",
            "identifiers": [
                {"channel_type": "whatsapp", "identifier": "+5191"},
                {"channel_type": "whatsapp", "identifier": "+5191"},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_person_by_id(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_person(client, headers)
    r = await client.get(f"{CRM}/persons/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]


async def test_get_person_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CRM}/persons/nope-404", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


async def test_update_person(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_person(client, headers, first_name="Ana")
    r = await client.put(
        f"{CRM}/persons/{created['id']}",
        json={"first_name": "Anabel", "notes": "VIP", "active": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["first_name"] == "Anabel"
    assert data["notes"] == "VIP"
    assert data["active"] is False


async def test_update_person_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(
        f"{CRM}/persons/nope", json={"first_name": "X"}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_delete_person(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_person(client, headers)
    r = await client.delete(f"{CRM}/persons/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # Tras soft-delete ya no se encuentra.
    r2 = await client.get(f"{CRM}/persons/{created['id']}", headers=headers)
    assert r2.status_code == 404


async def test_delete_person_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{CRM}/persons/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_persons(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_person(client, headers, first_name="Ana", last_name="Uno")
    await create_person(client, headers, first_name="Beto", last_name="Dos")
    r = await client.post(
        f"{CRM}/persons/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total"] >= 2
    assert len(body["items"]) >= 2


async def test_list_persons_filter_by_name(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_person(client, headers, first_name="Mariana", last_name="Filtro")
    body = {
        "pagination": {"skip": 0, "limit": 10},
        "filters": {
            "filters": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "first_name", "operator": "contains", "value": "Mariana"}
                    ],
                }
            ]
        },
    }
    r = await client.post(f"{CRM}/persons/list", json=body, headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert all("Mariana" in i["first_name"] for i in items)
    assert items


async def test_list_persons_deeplink_filters_noop(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Los deep-link filters por *_id no rompen el listado (EXISTS correlados)."""
    headers = await auth_headers(client, admin_credentials)
    await create_person(client, headers)
    r = await client.post(
        f"{CRM}/persons/list?has_active_lead=false",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def test_list_active_persons(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_person(
        client,
        headers,
        identifiers=[{"channel_type": "phone", "identifier": "+51777", "is_primary": True}],
    )
    r = await client.get(f"{CRM}/persons/active", headers=headers)
    assert r.status_code == 200, r.text
    # Lista cruda (sin envelope).
    rows = r.json()
    assert isinstance(rows, list)
    assert any(p["primary_identifier"] for p in rows)


async def test_search_person_by_query(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_person(client, headers, first_name="Zoraida", last_name="Buscable")
    r = await client.get(f"{CRM}/persons/search?q=Zoraida", headers=headers)
    assert r.status_code == 200, r.text
    options = r.json()["data"]
    assert any("Zoraida" in o["full_name"] for o in options)


async def test_search_person_by_identifier(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_person(
        client,
        headers,
        identifiers=[{"channel_type": "whatsapp", "identifier": "+51555444333"}],
    )
    r = await client.get(
        f"{CRM}/persons/search",
        params={"channel_type": "whatsapp", "identifier": "+51555444333"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1


async def test_search_no_match_returns_empty(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CRM}/persons/search?q=inexistente-zzz", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_persons_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{CRM}/persons/active")
    assert r.status_code == 401
