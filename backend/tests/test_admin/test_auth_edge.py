"""Casos de borde del service de auth no cubiertos por test_auth.py:
login de usuario deshabilitado, refresh con tokens malformados/del tipo
equivocado/de sesión inexistente, logout con token muerto. Cubre las ramas
de error de app/modules/admin/services/auth.py."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.security import create_access_token

PREFIX = "/api/v1/admin"


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    r = await client.post(f"{PREFIX}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


# ── login ──────────────────────────────────────────


async def test_login_disabled_user(client: AsyncClient, admin_credentials: dict) -> None:
    """Un usuario con active=False no puede loguear aunque la clave sea correcta."""
    headers = await _headers(client, admin_credentials)
    email = f"disabled-{uuid.uuid4().hex[:8]}@example.com"
    password = "DisabledUser123"
    created = await client.post(
        f"{PREFIX}/users",
        json={
            "email": email,
            "first_name": "Dis",
            "last_name": "Abled",
            "password": password,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["data"]["id"]
    # Confirmar que puede loguear estando activo.
    ok = await client.post(f"{PREFIX}/auth/login", json={"email": email, "password": password})
    assert ok.status_code == 200, ok.text
    # Deshabilitarlo.
    deact = await client.put(
        f"{PREFIX}/users/{user_id}", json={"active": False}, headers=headers
    )
    assert deact.status_code == 200, deact.text
    # Ahora el login debe fallar con 401.
    blocked = await client.post(
        f"{PREFIX}/auth/login", json={"email": email, "password": password}
    )
    assert blocked.status_code == 401, blocked.text


# ── refresh ────────────────────────────────────────


async def test_refresh_invalid_token(client: AsyncClient) -> None:
    r = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": "garbage.not.jwt"})
    assert r.status_code == 401, r.text


async def test_refresh_wrong_token_type(client: AsyncClient, admin_credentials: dict) -> None:
    """Pasar un access token donde se espera un refresh → 401 (type != refresh)."""
    login = (await client.post(f"{PREFIX}/auth/login", json=admin_credentials)).json()
    access = login["tokens"]["access_token"]
    r = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401, r.text


async def test_refresh_unknown_family(client: AsyncClient) -> None:
    """Un refresh token válido en forma pero de una familia inexistente → 401."""
    from app.core.security import create_refresh_token

    token, _family, _jti = create_refresh_token(str(uuid.uuid4()))
    r = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 401, r.text


# ── logout ─────────────────────────────────────────


async def test_logout_with_dead_token_is_ok(client: AsyncClient) -> None:
    """logout con un token ilegible no explota (return temprano)."""
    r = await client.post(f"{PREFIX}/auth/logout", json={"refresh_token": "totally-invalid"})
    assert r.status_code == 200, r.text


async def test_logout_with_access_token_no_family(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """logout con un access token (sin claim family) hace return sin revocar nada."""
    token = create_access_token(subject=str(uuid.uuid4()), roles=[], permissions=[])
    r = await client.post(f"{PREFIX}/auth/logout", json={"refresh_token": token})
    assert r.status_code == 200, r.text
