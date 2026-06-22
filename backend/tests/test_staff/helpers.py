"""
Helpers compartidos por los tests del módulo `staff`.

Crean los prerequisitos vía la API pública en orden de dependencias
(vertical/branch/office del catálogo+clínica → doctor → availability), usando el
token del admin sembrado (tiene TODOS los permisos). Mantener los payloads
mínimos y válidos para no chocar con los validators de Pydantic.
"""

from __future__ import annotations

import itertools

from httpx import AsyncClient

ADMIN_AUTH = "/api/v1/admin/auth"
CATALOG = "/api/v1/catalog"
CLINIC = "/api/v1/clinic"
STAFF = "/api/v1/staff"

# Contador global para generar codes/emails únicos por test sin colisiones.
_seq = itertools.count(1)


def _next() -> int:
    return next(_seq)


async def login(client: AsyncClient, credentials: dict) -> str:
    r = await client.post(f"{ADMIN_AUTH}/login", json=credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def admin_headers(client: AsyncClient, credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await login(client, credentials)}"}


async def create_vertical(client: AsyncClient, headers: dict) -> str:
    n = _next()
    r = await client.post(
        f"{CATALOG}/verticals",
        json={"code": f"vert_{n}", "name": f"Vertical {n}"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_branch(client: AsyncClient, headers: dict) -> str:
    n = _next()
    r = await client.post(
        f"{CLINIC}/branches",
        json={
            "code": f"branch_{n}",
            "name": f"Sede {n}",
            "address_line": "Av. Siempre Viva 123",
            "city": "Lima",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_office(client: AsyncClient, headers: dict, branch_id: str) -> str:
    n = _next()
    r = await client.post(
        f"{CLINIC}/offices",
        json={
            "branch_id": branch_id,
            "code": f"OFF-{n}",
            "name": f"Consultorio {n}",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_doctor(
    client: AsyncClient,
    headers: dict,
    *,
    branch_ids: list[str] | None = None,
    vertical_ids: list[str] | None = None,
    password: str | None = None,
    email: str | None = None,
) -> dict:
    """Crea un doctor (User + Doctor) y devuelve el cuerpo completo de la
    respuesta (incluye `data` con el DoctorDetail y `generated_password`)."""
    n = _next()
    user: dict = {
        "email": email or f"doctor_{n}@example.com",
        "first_name": "Doc",
        "last_name": f"Apellido{n}",
    }
    if password is not None:
        user["password"] = password
    payload: dict = {"user": user}
    if branch_ids is not None:
        payload["branch_ids"] = branch_ids
    if vertical_ids is not None:
        payload["vertical_ids"] = vertical_ids
    r = await client.post(f"{STAFF}/doctors", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()
