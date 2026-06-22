"""
Tests de integración del CRUD de ChannelAccount (service `channel_account`).
Happy paths + bordes: 404, 409 (identificador duplicado), validación 422, soft-delete,
edición con re-chequeo de unicidad, descarte de null en campos NOT NULL.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.test_conversations.helpers import (
    CONV,
    auth_headers,
    create_channel_account,
)

pytestmark = pytest.mark.rf("RF-E05-CHANNEL")


async def test_create_and_get_channel_account(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(
        client,
        headers,
        name="Soporte WA",
        external_identifier="111222333",
        secret_name="proj/sec/wa",
        webhook_verify_token="verify-tok",
        phone_number_id="PN123",
    )
    assert ca["name"] == "Soporte WA"
    assert ca["channel_type"] == "whatsapp"
    # El secreto NUNCA es valor crudo: solo flags derivados + el NOMBRE del recurso.
    assert ca["credentials_configured"] is True
    assert ca["has_verify_token"] is True
    assert ca["secret_name"] == "proj/sec/wa"
    assert ca["active"] is True

    r = await client.get(f"{CONV}/channel-accounts/{ca['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == ca["id"]


async def test_create_without_secret_flags_false(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="no-secret-1")
    assert ca["credentials_configured"] is False
    assert ca["has_verify_token"] is False


async def test_duplicate_external_identifier_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_channel_account(client, headers, external_identifier="dup-999")
    r = await client.post(
        f"{CONV}/channel-accounts",
        json={
            "channel_type": "whatsapp",
            "name": "Otra cuenta",
            "external_identifier": "dup-999",
        },
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CHANNEL_ACCOUNT_EXTERNAL_TAKEN"


async def test_get_missing_channel_account_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CONV}/channel-accounts/does-not-exist", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CHANNEL_ACCOUNT_NOT_FOUND"


async def test_create_invalid_payload_422(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    # name vacío viola min_length=1
    r = await client.post(
        f"{CONV}/channel-accounts",
        json={"channel_type": "whatsapp", "name": "", "external_identifier": "x"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_update_channel_account(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="upd-1")
    r = await client.put(
        f"{CONV}/channel-accounts/{ca['id']}",
        json={"name": "Renombrada", "active": False, "phone_number_id": "PN999"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Renombrada"
    assert data["active"] is False
    assert data["phone_number_id"] == "PN999"


async def test_update_null_required_field_is_ignored(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Un null EXPLÍCITO en name (NOT NULL) se descarta (no blanquea la columna)."""
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(
        client, headers, name="Original", external_identifier="upd-null-1"
    )
    r = await client.put(
        f"{CONV}/channel-accounts/{ca['id']}",
        json={"name": None, "phone_number_id": "PNX"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Original"  # no se blanqueó
    assert data["phone_number_id"] == "PNX"


async def test_update_external_identifier_clash_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_channel_account(client, headers, external_identifier="taken-aaa")
    ca2 = await create_channel_account(client, headers, external_identifier="free-bbb")
    r = await client.put(
        f"{CONV}/channel-accounts/{ca2['id']}",
        json={"external_identifier": "taken-aaa"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CHANNEL_ACCOUNT_EXTERNAL_TAKEN"


async def test_update_missing_channel_account_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(
        f"{CONV}/channel-accounts/nope",
        json={"name": "X"},
        headers=headers,
    )
    assert r.status_code == 404, r.text


async def test_list_paginated_and_active(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_channel_account(client, headers, name="Alpha", external_identifier="list-a")
    inactive = await create_channel_account(
        client, headers, name="Beta", external_identifier="list-b"
    )
    await client.put(
        f"{CONV}/channel-accounts/{inactive['id']}",
        json={"active": False},
        headers=headers,
    )

    r = await client.post(
        f"{CONV}/channel-accounts/list",
        json={"pagination": {"skip": 0, "limit": 50}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total"] >= 2
    assert any(it["created_by_user"] is not None for it in body["items"])

    # /active devuelve lista CRUDA (sin envelope) y excluye la deshabilitada.
    r = await client.get(f"{CONV}/channel-accounts/active", headers=headers)
    assert r.status_code == 200, r.text
    active_list = r.json()
    assert isinstance(active_list, list)
    names = {opt["name"] for opt in active_list}
    assert "Alpha" in names
    assert "Beta" not in names


async def test_list_filtered_by_active(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    await create_channel_account(client, headers, name="Filtrable", external_identifier="filt-1")
    r = await client.post(
        f"{CONV}/channel-accounts/list",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "filters": {
                "filters": [
                    {
                        "operator": "AND",
                        "conditions": [{"field": "active", "operator": "eq", "value": True}],
                    }
                ]
            },
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert all(it["active"] is True for it in r.json()["data"]["items"])


async def test_soft_delete_channel_account(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="del-1")
    r = await client.delete(f"{CONV}/channel-accounts/{ca['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # Tras soft-delete ya no se encuentra.
    r = await client.get(f"{CONV}/channel-accounts/{ca['id']}", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_missing_channel_account_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{CONV}/channel-accounts/missing", headers=headers)
    assert r.status_code == 404, r.text


async def test_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{CONV}/channel-accounts/active")
    assert r.status_code in (401, 403), r.text
