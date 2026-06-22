"""
Tests de integración del self-service `/api/v1/staff/me`.

Cada función resuelve el Doctor desde el token. Como el admin sembrado NO es
doctor, lo usamos para el path 403 NOT_A_DOCTOR; para los happy paths creamos un
doctor (con su password conocido) y nos logueamos como él — el rol DOCTOR trae
los permisos MY_* necesarios.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_staff.helpers import (
    admin_headers,
    create_branch,
    create_doctor,
    create_office,
    login,
)

STAFF = "/api/v1/staff"


async def _doctor_login(
    client: AsyncClient, admin_h: dict, *, branch_ids: list[str] | None = None
) -> tuple[dict, dict]:
    """Crea un doctor y devuelve (detalle, headers del doctor logueado)."""
    password = "DoctorPass123"
    n_email = f"me_doctor_{id(branch_ids)}@example.com"
    body = await create_doctor(
        client, admin_h, branch_ids=branch_ids, password=password, email=n_email
    )
    token = await login(client, {"email": n_email, "password": password})
    return body["data"], {"Authorization": f"Bearer {token}"}


async def test_get_my_doctor_ok(client: AsyncClient, admin_credentials: dict) -> None:
    admin_h = await admin_headers(client, admin_credentials)
    detail, doc_h = await _doctor_login(client, admin_h)
    r = await client.get(f"{STAFF}/me/doctor", headers=doc_h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == detail["id"]


async def test_get_my_doctor_no_doctor_403(
    client: AsyncClient, admin_credentials: dict
) -> None:
    # El admin tiene el permiso MY_DOCTOR_PROFILE_READ pero NO es doctor.
    admin_h = await admin_headers(client, admin_credentials)
    r = await client.get(f"{STAFF}/me/doctor", headers=admin_h)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "NOT_A_DOCTOR"


async def test_update_my_doctor_ok(client: AsyncClient, admin_credentials: dict) -> None:
    admin_h = await admin_headers(client, admin_credentials)
    detail, doc_h = await _doctor_login(client, admin_h)
    r = await client.put(
        f"{STAFF}/me/doctor",
        json={"bio": "Actualizo mi propia bio", "slot_duration_min": 20},
        headers=doc_h,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["bio"] == "Actualizo mi propia bio"
    assert data["slot_duration_min"] == 20


async def test_update_my_doctor_no_doctor_403(
    client: AsyncClient, admin_credentials: dict
) -> None:
    admin_h = await admin_headers(client, admin_credentials)
    r = await client.put(f"{STAFF}/me/doctor", json={"bio": "x"}, headers=admin_h)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "NOT_A_DOCTOR"


async def test_my_availability_crud(client: AsyncClient, admin_credentials: dict) -> None:
    admin_h = await admin_headers(client, admin_credentials)
    branch_id = await create_branch(client, admin_h)
    office_id = await create_office(client, admin_h, branch_id)
    _detail, doc_h = await _doctor_login(client, admin_h, branch_ids=[branch_id])

    block = {
        "branch_id": branch_id,
        "office_id": office_id,
        "date": "2026-08-01",
        "opens_at": "08:00:00",
        "closes_at": "13:00:00",
    }

    # Create.
    r = await client.post(
        f"{STAFF}/me/availability", json={"blocks": [block]}, headers=doc_h
    )
    assert r.status_code == 201, r.text
    block_id = r.json()["data"][0]["id"]

    # List.
    r = await client.get(f"{STAFF}/me/availability", headers=doc_h)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    # Update.
    r = await client.put(
        f"{STAFF}/me/availability/{block_id}",
        json={"closes_at": "12:00:00"},
        headers=doc_h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["closes_at"] == "12:00:00"

    # Delete.
    r = await client.delete(f"{STAFF}/me/availability/{block_id}", headers=doc_h)
    assert r.status_code == 204, r.text
    r = await client.get(f"{STAFF}/me/availability", headers=doc_h)
    assert r.json()["data"] == []


async def test_my_availability_no_doctor_403(
    client: AsyncClient, admin_credentials: dict
) -> None:
    admin_h = await admin_headers(client, admin_credentials)
    r = await client.get(f"{STAFF}/me/availability", headers=admin_h)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "NOT_A_DOCTOR"

    r = await client.post(
        f"{STAFF}/me/availability",
        json={
            "blocks": [
                {
                    "branch_id": "b",
                    "office_id": "o",
                    "date": "2026-08-01",
                    "opens_at": "08:00:00",
                    "closes_at": "13:00:00",
                }
            ]
        },
        headers=admin_h,
    )
    assert r.status_code == 403, r.text

    r = await client.put(
        f"{STAFF}/me/availability/ghost", json={"opens_at": "09:00:00"}, headers=admin_h
    )
    assert r.status_code == 403, r.text

    r = await client.delete(f"{STAFF}/me/availability/ghost", headers=admin_h)
    assert r.status_code == 403, r.text
