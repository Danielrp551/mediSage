"""Integración del service de users: CRUD, casos de borde (404, 409, validación)
y self-service change-password. Cubre app/modules/admin/services/user.py."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

PREFIX = "/api/v1/admin"


async def _token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post(f"{PREFIX}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, admin_credentials)}"}


def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


async def _active_permission_ids(
    client: AsyncClient, headers: dict[str, str], n: int = 1
) -> list[str]:
    r = await client.get(f"{PREFIX}/permissions/active", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()  # /active devuelve lista cruda
    assert len(items) >= n
    return [p["id"] for p in items[:n]]


async def _create_role(client: AsyncClient, headers: dict[str, str]) -> str:
    name = f"Role-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        f"{PREFIX}/roles",
        json={"name": name, "description": "tmp role"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


# ── create ─────────────────────────────────────────


async def test_create_user_with_generated_password(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    email = _unique_email()
    r = await client.post(
        f"{PREFIX}/users",
        json={"email": email, "first_name": "Ada", "last_name": "Lovelace"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["success"] is True
    assert body["data"]["email"] == email
    assert body["data"]["full_name"]
    # Sin password en el payload → el service genera uno y lo devuelve una vez.
    assert body["generated_password"]


async def test_create_user_with_explicit_password_hides_it(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/users",
        json={
            "email": _unique_email(),
            "first_name": "Grace",
            "last_name": "Hopper",
            "password": "SuperSecret123",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    # Con password explícito → no se expone nada.
    assert r.json()["generated_password"] is None


async def test_create_user_with_roles_and_permissions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    perm_ids = await _active_permission_ids(client, headers, n=2)
    role_id = await _create_role(client, headers)
    r = await client.post(
        f"{PREFIX}/users",
        json={
            "email": _unique_email(),
            "first_name": "Alan",
            "last_name": "Turing",
            "role_ids": [role_id],
            "permission_ids": perm_ids,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["roles_count"] == 1
    assert data["permissions_count"] == 2
    assert {p["id"] for p in data["permissions"]} == set(perm_ids)


async def test_create_user_duplicate_email_conflict(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    email = _unique_email()
    first = await client.post(
        f"{PREFIX}/users",
        json={"email": email, "first_name": "Edsger", "last_name": "Dijkstra"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    dup = await client.post(
        f"{PREFIX}/users",
        json={"email": email, "first_name": "Other", "last_name": "Person"},
        headers=headers,
    )
    assert dup.status_code == 409, dup.text
    assert dup.json()["success"] is False


async def test_create_user_unknown_role_is_bad_request(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/users",
        json={
            "email": _unique_email(),
            "first_name": "Bad",
            "last_name": "Role",
            "role_ids": ["does-not-exist"],
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text


async def test_create_user_unknown_permission_is_bad_request(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/users",
        json={
            "email": _unique_email(),
            "first_name": "Bad",
            "last_name": "Perm",
            "permission_ids": ["nope-nope"],
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text


async def test_create_user_invalid_email_validation(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/users",
        json={"email": "not-an-email", "first_name": "X", "last_name": "Y"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


# ── read ───────────────────────────────────────────


async def test_get_user_by_id(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/users",
        json={"email": _unique_email(), "first_name": "Read", "last_name": "Me"},
        headers=headers,
    )
    user_id = created.json()["data"]["id"]
    r = await client.get(f"{PREFIX}/users/{user_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == user_id


async def test_get_user_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/users/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_users_paginated_and_filtered(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    email = _unique_email("filterme")
    await client.post(
        f"{PREFIX}/users",
        json={"email": email, "first_name": "Filter", "last_name": "Target"},
        headers=headers,
    )
    r = await client.post(
        f"{PREFIX}/users/list",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "sorting": {"sort_by": "created_on", "sort_order": "desc"},
            "filters": {
                "filters": [
                    {
                        "operator": "AND",
                        "conditions": [
                            {"field": "email", "operator": "contains", "value": "filterme"}
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
    assert any(u["email"] == email for u in body["items"])


# ── update ─────────────────────────────────────────


async def test_update_user_fields_roles_permissions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/users",
        json={"email": _unique_email(), "first_name": "Old", "last_name": "Name"},
        headers=headers,
    )
    user_id = created.json()["data"]["id"]
    perm_ids = await _active_permission_ids(client, headers, n=1)
    role_id = await _create_role(client, headers)
    new_email = _unique_email("updated")
    r = await client.put(
        f"{PREFIX}/users/{user_id}",
        json={
            "email": new_email,
            "first_name": "New",
            "active": False,
            "role_ids": [role_id],
            "permission_ids": perm_ids,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["email"] == new_email
    assert data["first_name"] == "New"
    assert data["active"] is False
    assert data["roles_count"] == 1
    assert data["permissions_count"] == 1


async def test_update_user_clear_roles(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    role_id = await _create_role(client, headers)
    created = await client.post(
        f"{PREFIX}/users",
        json={
            "email": _unique_email(),
            "first_name": "HasRole",
            "last_name": "User",
            "role_ids": [role_id],
        },
        headers=headers,
    )
    user_id = created.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/users/{user_id}", json={"role_ids": []}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["roles_count"] == 0


async def test_update_user_not_found(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(
        f"{PREFIX}/users/{uuid.uuid4()}",
        json={"first_name": "Ghost"},
        headers=headers,
    )
    assert r.status_code == 404, r.text


async def test_update_user_email_conflict(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    taken = _unique_email("taken")
    await client.post(
        f"{PREFIX}/users",
        json={"email": taken, "first_name": "A", "last_name": "B"},
        headers=headers,
    )
    other = await client.post(
        f"{PREFIX}/users",
        json={"email": _unique_email(), "first_name": "C", "last_name": "D"},
        headers=headers,
    )
    other_id = other.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/users/{other_id}", json={"email": taken}, headers=headers
    )
    assert r.status_code == 409, r.text


async def test_update_user_unknown_permission_bad_request(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    created = await client.post(
        f"{PREFIX}/users",
        json={"email": _unique_email(), "first_name": "E", "last_name": "F"},
        headers=headers,
    )
    user_id = created.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/users/{user_id}",
        json={"permission_ids": ["ghost-perm"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text


# ── change password (self-service) ─────────────────


async def test_change_my_password_success_and_login(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    new_password = "BrandNewPass456"
    r = await client.post(
        f"{PREFIX}/users/me/change-password",
        json={
            "current_password": admin_credentials["password"],
            "new_password": new_password,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["detail"]
    # La nueva contraseña debe permitir login; la vieja ya no.
    relog = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": admin_credentials["email"], "password": new_password},
    )
    assert relog.status_code == 200, relog.text
    old = await client.post(f"{PREFIX}/auth/login", json=admin_credentials)
    assert old.status_code == 401


async def test_change_my_password_wrong_current(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/users/me/change-password",
        json={"current_password": "totally-wrong", "new_password": "AnotherPass789"},
        headers=headers,
    )
    assert r.status_code == 401, r.text
