"""Integración del service de permissions: CRUD, /active, casos de borde
(404, 409, validación). Cubre app/modules/admin/services/permission.py."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

PREFIX = "/api/v1/admin"


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    r = await client.post(f"{PREFIX}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def _code() -> str:
    return f"TEST_{uuid.uuid4().hex[:8].upper()}"


# ── create ─────────────────────────────────────────


async def test_create_permission(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    code = _code()
    r = await client.post(
        f"{PREFIX}/permissions",
        json={"code": code, "name": "Test Permission", "module": "testing"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"] == code
    assert data["module"] == "testing"
    assert data["active"] is True
    assert data["description"] == ""


async def test_create_permission_with_description(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/permissions",
        json={
            "code": _code(),
            "name": "Described Perm",
            "description": "does something",
            "module": "testing",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["description"] == "does something"


async def test_create_permission_duplicate_code_conflict(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    code = _code()
    first = await client.post(
        f"{PREFIX}/permissions",
        json={"code": code, "name": "First", "module": "testing"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    dup = await client.post(
        f"{PREFIX}/permissions",
        json={"code": code, "name": "Second", "module": "testing"},
        headers=headers,
    )
    assert dup.status_code == 409, dup.text


async def test_create_permission_validation(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    # name demasiado corto (min_length=2) → 422
    r = await client.post(
        f"{PREFIX}/permissions",
        json={"code": _code(), "name": "X", "module": "testing"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


# ── read ───────────────────────────────────────────


async def test_get_permission_by_id(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/permissions",
        json={"code": _code(), "name": "Readable", "module": "testing"},
        headers=headers,
    )
    perm_id = created.json()["data"]["id"]
    r = await client.get(f"{PREFIX}/permissions/{perm_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == perm_id


async def test_get_permission_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/permissions/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_active_permissions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/permissions/active", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()  # lista cruda
    assert len(items) >= 1
    # Los seedeados incluyen MENU-HOME y USERS_VIEW.
    codes = {p["code"] for p in items}
    assert "USERS_VIEW" in codes


async def test_list_permissions_paginated_filtered(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    code = _code()
    await client.post(
        f"{PREFIX}/permissions",
        json={"code": code, "name": "Filter Perm", "module": "filtermod"},
        headers=headers,
    )
    r = await client.post(
        f"{PREFIX}/permissions/list",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "filters": {
                "filters": [
                    {
                        "operator": "AND",
                        "conditions": [
                            {"field": "module", "operator": "eq", "value": "filtermod"}
                        ],
                    }
                ]
            },
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total"] >= 1
    assert all(p["module"] == "filtermod" for p in body["items"])


# ── update ─────────────────────────────────────────


async def test_update_permission_fields(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/permissions",
        json={"code": _code(), "name": "Before", "module": "testing"},
        headers=headers,
    )
    perm_id = created.json()["data"]["id"]
    new_code = _code()
    r = await client.put(
        f"{PREFIX}/permissions/{perm_id}",
        json={
            "code": new_code,
            "name": "After",
            "description": "updated",
            "module": "updated_mod",
            "active": False,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["code"] == new_code
    assert data["name"] == "After"
    assert data["module"] == "updated_mod"
    assert data["active"] is False


async def test_update_permission_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(
        f"{PREFIX}/permissions/{uuid.uuid4()}",
        json={"name": "Ghost"},
        headers=headers,
    )
    assert r.status_code == 404, r.text


async def test_update_permission_code_conflict(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    taken = _code()
    await client.post(
        f"{PREFIX}/permissions",
        json={"code": taken, "name": "Taken", "module": "testing"},
        headers=headers,
    )
    other = await client.post(
        f"{PREFIX}/permissions",
        json={"code": _code(), "name": "Other", "module": "testing"},
        headers=headers,
    )
    other_id = other.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/permissions/{other_id}", json={"code": taken}, headers=headers
    )
    assert r.status_code == 409, r.text
