"""Integración del service de roles: CRUD, /active, casos de borde
(404, 409, permiso desconocido/inactivo). Cubre app/modules/admin/services/role.py."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

PREFIX = "/api/v1/admin"


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    r = await client.post(f"{PREFIX}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def _name() -> str:
    return f"Role-{uuid.uuid4().hex[:8]}"


async def _active_permission_ids(
    client: AsyncClient, headers: dict[str, str], n: int = 1
) -> list[str]:
    r = await client.get(f"{PREFIX}/permissions/active", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= n
    return [p["id"] for p in items[:n]]


# ── create ─────────────────────────────────────────


async def test_create_role_minimal(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    name = _name()
    r = await client.post(
        f"{PREFIX}/roles",
        json={"name": name, "description": "A role"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["name"] == name
    assert data["active"] is True
    assert data["permissions_count"] == 0


async def test_create_role_with_permissions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    perm_ids = await _active_permission_ids(client, headers, n=3)
    r = await client.post(
        f"{PREFIX}/roles",
        json={"name": _name(), "description": "with perms", "permission_ids": perm_ids},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["permissions_count"] == 3
    assert {p["id"] for p in data["permissions"]} == set(perm_ids)


async def test_create_role_duplicate_name_conflict(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    name = _name()
    first = await client.post(
        f"{PREFIX}/roles", json={"name": name, "description": "first"}, headers=headers
    )
    assert first.status_code == 201, first.text
    dup = await client.post(
        f"{PREFIX}/roles", json={"name": name, "description": "second"}, headers=headers
    )
    assert dup.status_code == 409, dup.text


async def test_create_role_unknown_permission_bad_request(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/roles",
        json={"name": _name(), "description": "x", "permission_ids": ["ghost"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text


async def test_create_role_name_too_short_validation(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/roles", json={"name": "X", "description": "y"}, headers=headers
    )
    assert r.status_code == 422, r.text


# ── read ───────────────────────────────────────────


async def test_get_role_by_id(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/roles", json={"name": _name(), "description": "z"}, headers=headers
    )
    role_id = created.json()["data"]["id"]
    r = await client.get(f"{PREFIX}/roles/{role_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == role_id


async def test_get_role_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/roles/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_active_roles(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    name = _name()
    await client.post(
        f"{PREFIX}/roles", json={"name": name, "description": "active one"}, headers=headers
    )
    r = await client.get(f"{PREFIX}/roles/active", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()  # lista cruda
    assert any(role["name"] == name for role in items)
    # Incluye el ADMIN seedeado.
    assert any(role["name"] == "ADMIN" for role in items)


async def test_list_roles_paginated(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/roles/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total"] >= 1


# ── update ─────────────────────────────────────────


async def test_update_role_fields_and_permissions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/roles", json={"name": _name(), "description": "before"}, headers=headers
    )
    role_id = created.json()["data"]["id"]
    perm_ids = await _active_permission_ids(client, headers, n=2)
    new_name = _name()
    r = await client.put(
        f"{PREFIX}/roles/{role_id}",
        json={
            "name": new_name,
            "description": "after",
            "active": False,
            "permission_ids": perm_ids,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == new_name
    assert data["description"] == "after"
    assert data["active"] is False
    assert data["permissions_count"] == 2


async def test_update_role_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(
        f"{PREFIX}/roles/{uuid.uuid4()}", json={"description": "x"}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_update_role_name_conflict(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    taken = _name()
    await client.post(
        f"{PREFIX}/roles", json={"name": taken, "description": "x"}, headers=headers
    )
    other = await client.post(
        f"{PREFIX}/roles", json={"name": _name(), "description": "y"}, headers=headers
    )
    other_id = other.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/roles/{other_id}", json={"name": taken}, headers=headers
    )
    assert r.status_code == 409, r.text


async def test_update_role_clear_permissions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    perm_ids = await _active_permission_ids(client, headers, n=1)
    created = await client.post(
        f"{PREFIX}/roles",
        json={"name": _name(), "description": "x", "permission_ids": perm_ids},
        headers=headers,
    )
    role_id = created.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/roles/{role_id}", json={"permission_ids": []}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["permissions_count"] == 0


async def test_update_role_inactive_permission_bad_request(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Asignar un permiso inactivo debe rechazarse (BadRequest)."""
    headers = await _headers(client, admin_credentials)
    # Crear un permiso y desactivarlo.
    code = f"TMP_{uuid.uuid4().hex[:8].upper()}"
    created_perm = await client.post(
        f"{PREFIX}/permissions",
        json={"code": code, "name": "Temp Perm", "module": "tmp"},
        headers=headers,
    )
    perm_id = created_perm.json()["data"]["id"]
    deact = await client.put(
        f"{PREFIX}/permissions/{perm_id}", json={"active": False}, headers=headers
    )
    assert deact.status_code == 200, deact.text

    created_role = await client.post(
        f"{PREFIX}/roles", json={"name": _name(), "description": "x"}, headers=headers
    )
    role_id = created_role.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/roles/{role_id}",
        json={"permission_ids": [perm_id]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert "inactive" in r.json()["detail"].lower()
