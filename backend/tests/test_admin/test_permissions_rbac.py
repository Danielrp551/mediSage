"""`RequirePermission` blocks calls when the token's permissions claim is missing."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.security import create_access_token


async def test_admin_can_list_users(client: AsyncClient, admin_credentials: dict) -> None:
    login = (await client.post("/api/v1/admin/auth/login", json=admin_credentials)).json()
    token = login["tokens"]["access_token"]

    response = await client.post(
        "/api/v1/admin/users/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 1


async def test_token_without_permission_is_forbidden(client: AsyncClient) -> None:
    """A handcrafted token with no permissions should still authenticate
    but be blocked at the RBAC layer."""
    # Use the seeded admin id (deterministic).
    token = create_access_token(
        subject="00000000-0000-0000-0000-000000000001",
        roles=["ADMIN"],
        permissions=[],  # ← no permissions in claim
    )
    response = await client.post(
        "/api/v1/admin/users/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
