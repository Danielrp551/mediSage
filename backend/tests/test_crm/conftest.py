"""
Helpers compartidos por los tests de integración del módulo crm.

Reusan el fixture async `client` del conftest raíz (SQLite en memoria, admin
sembrado con TODOS los permisos + catálogos de estado lead/customer + matriz).
"""

from __future__ import annotations

from httpx import AsyncClient

CRM = "/api/v1/crm"
ADMIN = "/api/v1/admin"


async def token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post(f"{ADMIN}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def auth_headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await token(client, admin_credentials)}"}


async def create_person(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    first_name: str = "Ana",
    last_name: str = "Perez",
    **extra,
) -> dict:
    body = {"first_name": first_name, "last_name": last_name, **extra}
    r = await client.post(f"{CRM}/persons", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def lead_status_options(client: AsyncClient, headers: dict[str, str]) -> dict[str, dict]:
    """Mapa code -> LeadStatusOption (de los estados seedeados)."""
    r = await client.get(f"{CRM}/lead-statuses/active", headers=headers)
    assert r.status_code == 200, r.text
    return {o["code"]: o for o in r.json()}


async def customer_status_options(
    client: AsyncClient, headers: dict[str, str]
) -> dict[str, dict]:
    r = await client.get(f"{CRM}/customer-statuses/active", headers=headers)
    assert r.status_code == 200, r.text
    return {o["code"]: o for o in r.json()}


async def asesor_role_id(client: AsyncClient, headers: dict[str, str]) -> str:
    r = await client.get(f"{ADMIN}/roles/active", headers=headers)
    assert r.status_code == 200, r.text
    roles = {role["name"]: role["id"] for role in r.json()}
    return roles["ASESOR"]


async def create_advisor(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    email: str = "asesor@example.com",
    first_name: str = "Carlos",
    last_name: str = "Asesor",
) -> str:
    """Crea un user con rol ASESOR y devuelve su id."""
    role_id = await asesor_role_id(client, headers)
    r = await client.post(
        f"{ADMIN}/users",
        json={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role_ids": [role_id],
            "password": "Asesor12345!",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]
