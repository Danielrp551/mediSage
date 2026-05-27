"""Auth flow: login, refresh rotation, logout revocation, /me."""

from __future__ import annotations

from httpx import AsyncClient


PREFIX = "/api/v1/admin/auth"


async def test_login_success(client: AsyncClient, admin_credentials: dict) -> None:
    response = await client.post(f"{PREFIX}/login", json=admin_credentials)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["user"]["email"] == admin_credentials["email"]
    assert "MENU-HOME" in body["user"]["permissions"]


async def test_login_bad_credentials(client: AsyncClient) -> None:
    response = await client.post(
        f"{PREFIX}/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False


async def test_login_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        f"{PREFIX}/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )
    assert response.status_code == 401


async def test_refresh_rotates_tokens(client: AsyncClient, admin_credentials: dict) -> None:
    login = (await client.post(f"{PREFIX}/login", json=admin_credentials)).json()
    refresh_token = login["tokens"]["refresh_token"]

    response = await client.post(f"{PREFIX}/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    new_tokens = response.json()["tokens"]
    assert new_tokens["access_token"] != login["tokens"]["access_token"]
    assert new_tokens["refresh_token"] != refresh_token


async def test_refresh_reuse_detection(client: AsyncClient, admin_credentials: dict) -> None:
    """Submitting the same refresh token twice must revoke the family."""
    login = (await client.post(f"{PREFIX}/login", json=admin_credentials)).json()
    original_refresh = login["tokens"]["refresh_token"]

    # First refresh rotates the token successfully.
    rotated = await client.post(f"{PREFIX}/refresh", json={"refresh_token": original_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["tokens"]["refresh_token"]

    # Replaying the OLD refresh token must fail — that's the reuse signal.
    replay = await client.post(f"{PREFIX}/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401
    assert "reuse" in replay.json()["detail"].lower()

    # And the family is now revoked — the freshly-issued refresh is also dead.
    revoked = await client.post(f"{PREFIX}/refresh", json={"refresh_token": new_refresh})
    assert revoked.status_code == 401


async def test_logout_revokes_family(client: AsyncClient, admin_credentials: dict) -> None:
    login = (await client.post(f"{PREFIX}/login", json=admin_credentials)).json()
    refresh_token = login["tokens"]["refresh_token"]

    logout = await client.post(f"{PREFIX}/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 200

    # Refresh should now fail — entire family is revoked.
    response = await client.post(f"{PREFIX}/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


async def test_me_requires_bearer(client: AsyncClient) -> None:
    response = await client.get(f"{PREFIX}/me")
    assert response.status_code == 401


async def test_me_returns_current_user(client: AsyncClient, admin_credentials: dict) -> None:
    login = (await client.post(f"{PREFIX}/login", json=admin_credentials)).json()
    token = login["tokens"]["access_token"]

    response = await client.get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == admin_credentials["email"]
    assert "ADMIN" in body["roles"]
