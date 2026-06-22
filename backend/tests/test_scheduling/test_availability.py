"""
Tests de integración de disponibilidad on-the-fly: POST /availability/compute y
/availability/check-slot. Ejercen el corazón del service `availability`
(compute_available_slots + validate_booking_invariants + check_slot).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_scheduling.helpers import (
    auth_headers,
    build_bookable_scenario,
)

COMPUTE = "/api/v1/scheduling/availability/compute"
CHECK = "/api/v1/scheduling/availability/check-slot"


async def test_compute_returns_slots(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await client.post(
        COMPUTE,
        json={
            "doctor_id": s.doctor_id,
            "product_id": s.product_id,
            "branch_id": s.branch_id,
            "office_id": s.office_id,
            "from_date": s.date,
            "to_date": s.date,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["duration_min"] == 30
    assert data["doctor_slot_duration_min"] == 30
    assert len(data["slots"]) > 0
    first = data["slots"][0]
    assert first["doctor_id"] == s.doctor_id
    assert first["office_id"] == s.office_id


async def test_compute_unknown_product_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await client.post(
        COMPUTE,
        json={
            "doctor_id": s.doctor_id,
            "product_id": "ghost-product",
            "from_date": s.date,
            "to_date": s.date,
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_compute_unknown_doctor_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await client.post(
        COMPUTE,
        json={
            "doctor_id": "ghost-doctor",
            "product_id": s.product_id,
            "from_date": s.date,
            "to_date": s.date,
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "DOCTOR_NOT_FOUND"


async def test_compute_inactive_doctor_empty(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers, doctor_active=False)
    r = await client.post(
        COMPUTE,
        json={
            "doctor_id": s.doctor_id,
            "product_id": s.product_id,
            "from_date": s.date,
            "to_date": s.date,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["slots"] == []


async def test_compute_range_validation_422(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await client.post(
        COMPUTE,
        json={
            "doctor_id": s.doctor_id,
            "product_id": s.product_id,
            "from_date": "2030-02-10",
            "to_date": "2030-02-01",  # to < from
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_check_slot_available(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await client.post(
        CHECK,
        json={
            "doctor_id": s.doctor_id,
            "office_id": s.office_id,
            "product_id": s.product_id,
            "scheduled_for": s.scheduled_for,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["available"] is True
    assert r.json()["data"]["reason"] is None


async def test_check_slot_outside_block_unavailable(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Un horario fuera del bloque de disponibilidad (06:00, antes de 08:00) → no
    available con reason NO_AVAILABILITY_BLOCK (BadRequest capturado por check_slot)."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    outside = s.scheduled_for.replace("T10:00", "T06:00")
    r = await client.post(
        CHECK,
        json={
            "doctor_id": s.doctor_id,
            "office_id": s.office_id,
            "product_id": s.product_id,
            "scheduled_for": outside,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["available"] is False
    assert r.json()["data"]["reason"] == "NO_AVAILABILITY_BLOCK"


async def test_check_slot_taken_after_booking(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Tras bookear el slot, check-slot del MISMO horario devuelve SLOT_TAKEN."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    booked = await client.post(
        "/api/v1/scheduling/appointments",
        json={
            "person_id": s.person_id,
            "doctor_id": s.doctor_id,
            "office_id": s.office_id,
            "product_id": s.product_id,
            "scheduled_for": s.scheduled_for,
        },
        headers=headers,
    )
    assert booked.status_code == 201, booked.text
    r = await client.post(
        CHECK,
        json={
            "doctor_id": s.doctor_id,
            "office_id": s.office_id,
            "product_id": s.product_id,
            "scheduled_for": s.scheduled_for,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["available"] is False
    assert r.json()["data"]["reason"] == "SLOT_TAKEN"


async def test_check_slot_unknown_office_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Un office inexistente PROPAGA 404 (no se interpreta como 'ocupado')."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await client.post(
        CHECK,
        json={
            "doctor_id": s.doctor_id,
            "office_id": "ghost-office",
            "product_id": s.product_id,
            "scheduled_for": s.scheduled_for,
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "OFFICE_NOT_FOUND"
