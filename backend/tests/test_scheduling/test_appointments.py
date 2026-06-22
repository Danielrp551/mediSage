"""
Tests de integración del service `appointment`: create/book (invariantes + SLOT_TAKEN),
list paginado, get detalle, update (changelog), delete (soft) y /me (agenda del doctor).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_scheduling.helpers import (
    appointment_payload,
    auth_headers,
    build_bookable_scenario,
)

PREFIX = "/api/v1/scheduling/appointments"
ME = "/api/v1/scheduling/me/appointments/list"


async def _book(client: AsyncClient, headers: dict, s, **overrides):
    return await client.post(PREFIX, json=appointment_payload(s, **overrides), headers=headers)


async def test_create_appointment_happy_path(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await _book(client, headers, s)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["person_id"] == s.person_id
    assert data["doctor_id"] == s.doctor_id
    assert data["branch_id"] == s.branch_id  # derivado del office
    assert data["duration_min"] == 30  # derivado del product
    assert data["status"]["code"] == "SCHEDULED"  # is_initial
    assert data["source"] == "advisor"
    # El history nace con la primera arista (None → SCHEDULED).
    assert len(data["status_history"]) == 1
    assert data["status_history"][0]["to_status"]["code"] == "SCHEDULED"


async def test_create_duplicate_slot_409(client: AsyncClient, admin_credentials: dict) -> None:
    """HU18 escenario 3: no duplicidad de citas en el mismo horario para el mismo doctor."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r1 = await _book(client, headers, s)
    assert r1.status_code == 201, r1.text
    r2 = await _book(client, headers, s)  # mismo doctor/office/horario
    assert r2.status_code == 409, r2.text
    assert r2.json()["code"] in ("SLOT_TAKEN", "OFFICE_SLOT_TAKEN")


async def test_create_unknown_product_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    r = await _book(client, headers, s, product_id="ghost")
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_create_inactive_doctor_400(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers, doctor_active=False)
    r = await _book(client, headers, s)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "DOCTOR_INACTIVE"


async def test_create_outside_availability_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    outside = s.scheduled_for.replace("T10:00", "T06:00")  # antes del bloque 08:00
    r = await _book(client, headers, s, scheduled_for=outside)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "NO_AVAILABILITY_BLOCK"


async def test_get_appointment_detail(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    created = await _book(client, headers, s)
    appt_id = created.json()["data"]["id"]
    r = await client.get(f"{PREFIX}/{appt_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == appt_id
    assert "change_log" in r.json()["data"]


async def test_get_appointment_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/ghost", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "APPOINTMENT_NOT_FOUND"


async def test_list_appointments(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    created = await _book(client, headers, s)
    appt_id = created.json()["data"]["id"]
    r = await client.post(
        f"{PREFIX}/list", json={"pagination": {"skip": 0, "limit": 10}}, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 1
    assert appt_id in {item["id"] for item in data["items"]}


async def test_list_filter_by_doctor(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    await _book(client, headers, s)
    r = await client.post(
        f"{PREFIX}/list",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "filters": {
                "filters": [
                    {
                        "operator": "AND",
                        "conditions": [
                            {"field": "doctor_id", "operator": "eq", "value": s.doctor_id}
                        ],
                    }
                ]
            },
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert items
    assert all(item["doctor_id"] == s.doctor_id for item in items)


async def test_update_appointment_notes_logs_change(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    created = await _book(client, headers, s, notes="original")
    appt_id = created.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/{appt_id}",
        json={"notes": "actualizada", "reason": "corrección"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["notes"] == "actualizada"
    log = data["change_log"]
    assert any(c["field_name"] == "notes" and c["new_value"] == "actualizada" for c in log)


async def test_update_appointment_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{PREFIX}/ghost", json={"notes": "x"}, headers=headers)
    assert r.status_code == 404, r.text


async def test_update_revalidates_invalid_combo_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Cambiar el office por uno inexistente revalida invariantes → 404 OFFICE_NOT_FOUND."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    created = await _book(client, headers, s)
    appt_id = created.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/{appt_id}", json={"office_id": "ghost-office"}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "OFFICE_NOT_FOUND"


async def test_delete_appointment_soft(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    created = await _book(client, headers, s)
    appt_id = created.json()["data"]["id"]
    r = await client.delete(f"{PREFIX}/{appt_id}", headers=headers)
    assert r.status_code == 204, r.text
    # Soft-deleted → get devuelve 404.
    g = await client.get(f"{PREFIX}/{appt_id}", headers=headers)
    assert g.status_code == 404, g.text


async def test_delete_appointment_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/ghost", headers=headers)
    assert r.status_code == 404, r.text


async def test_me_appointments_scoped_to_doctor(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """El admin no tiene perfil Doctor → /me devuelve página vacía (anti-IDOR)."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    await _book(client, headers, s)
    r = await client.post(ME, json={"pagination": {"skip": 0, "limit": 10}}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total"] == 0  # admin no es doctor
