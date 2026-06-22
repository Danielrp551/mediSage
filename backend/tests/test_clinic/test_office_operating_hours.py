"""
Tests de integración del service `office_operating_hours`.

El patrón semanal se gestiona con un reemplazo atómico (PUT). Cubre: GET vacío,
PUT con bloques, idempotencia del reemplazo, limpiar el patrón con [], office
inexistente (404), y validaciones 422 (closes <= opens, solapamiento mismo día).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_clinic.conftest import (
    CLINIC,
    auth_headers,
    create_branch,
    create_office,
)


async def _office_id(client: AsyncClient, headers: dict) -> str:
    branch = await create_branch(client, headers)
    office = await create_office(client, headers, branch["id"])
    return office["id"]


async def test_get_operating_hours_empty(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.get(f"{CLINIC}/offices/{office_id}/operating-hours", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_replace_operating_hours_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    payload = {
        "hours": [
            {"day_of_week": 0, "opens_at": "09:00:00", "closes_at": "13:00:00"},
            {"day_of_week": 0, "opens_at": "14:00:00", "closes_at": "18:00:00"},
            {"day_of_week": 1, "opens_at": "09:00:00", "closes_at": "17:00:00"},
        ]
    }
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours", json=payload, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 3
    # Ordered by day then opens_at.
    assert data[0]["day_of_week"] == 0
    assert data[0]["opens_at"] == "09:00:00"
    assert data[1]["opens_at"] == "14:00:00"
    assert all(b["id"] for b in data)


async def test_replace_operating_hours_idempotent(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    first = {"hours": [{"day_of_week": 2, "opens_at": "08:00:00", "closes_at": "12:00:00"}]}
    await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours", json=first, headers=headers
    )
    # Replace with a different pattern; the old block must be gone (not accumulated).
    second = {"hours": [{"day_of_week": 3, "opens_at": "10:00:00", "closes_at": "16:00:00"}]}
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours", json=second, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["day_of_week"] == 3


async def test_replace_operating_hours_clear(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours",
        json={"hours": [{"day_of_week": 0, "opens_at": "09:00:00", "closes_at": "17:00:00"}]},
        headers=headers,
    )
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours", json={"hours": []}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_operating_hours_office_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CLINIC}/offices/ghost/operating-hours", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "OFFICE_NOT_FOUND"


async def test_replace_operating_hours_office_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(
        f"{CLINIC}/offices/ghost/operating-hours",
        json={"hours": [{"day_of_week": 0, "opens_at": "09:00:00", "closes_at": "17:00:00"}]},
        headers=headers,
    )
    assert r.status_code == 404, r.text


async def test_replace_operating_hours_closes_before_opens_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours",
        json={"hours": [{"day_of_week": 0, "opens_at": "18:00:00", "closes_at": "09:00:00"}]},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_replace_operating_hours_overlap_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours",
        json={
            "hours": [
                {"day_of_week": 0, "opens_at": "09:00:00", "closes_at": "13:00:00"},
                {"day_of_week": 0, "opens_at": "12:00:00", "closes_at": "18:00:00"},
            ]
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_replace_operating_hours_invalid_day_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours",
        json={"hours": [{"day_of_week": 7, "opens_at": "09:00:00", "closes_at": "17:00:00"}]},
        headers=headers,
    )
    assert r.status_code == 422, r.text
