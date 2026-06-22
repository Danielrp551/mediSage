"""
Helpers compartidos por los tests de integración del módulo clinic.

Reutiliza el fixture async `client` del conftest raíz (BD sqlite en memoria +
admin sembrado con TODOS los permisos). Los prerequisitos (branch, vertical,
office) se crean vía la API pública en orden de dependencias.
"""

from __future__ import annotations

from httpx import AsyncClient

CLINIC = "/api/v1/clinic"
CATALOG = "/api/v1/catalog"
AUTH = "/api/v1/admin/auth"


async def auth_headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    r = await client.post(f"{AUTH}/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def branch_payload(code: str = "sede_lima", **overrides: object) -> dict:
    payload: dict = {
        "code": code,
        "name": "Sede Lima Centro",
        "address_line": "Av. Principal 123",
        "city": "Lima",
        "country": "PE",
        "timezone": "America/Lima",
    }
    payload.update(overrides)
    return payload


async def create_branch(
    client: AsyncClient, headers: dict, code: str = "sede_lima", **overrides: object
) -> dict:
    r = await client.post(
        f"{CLINIC}/branches", json=branch_payload(code, **overrides), headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def create_vertical(
    client: AsyncClient, headers: dict, code: str = "estetica"
) -> dict:
    r = await client.post(
        f"{CATALOG}/verticals",
        json={"code": code, "name": f"Vertical {code}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def office_payload(branch_id: str, code: str = "c-01", **overrides: object) -> dict:
    payload: dict = {
        "branch_id": branch_id,
        "code": code,
        "name": "Consultorio 01",
    }
    payload.update(overrides)
    return payload


async def create_office(
    client: AsyncClient,
    headers: dict,
    branch_id: str,
    code: str = "c-01",
    **overrides: object,
) -> dict:
    r = await client.post(
        f"{CLINIC}/offices",
        json=office_payload(branch_id, code, **overrides),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]
