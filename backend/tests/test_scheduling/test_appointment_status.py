"""
Tests de integración del catálogo AppointmentStatus + matriz de transiciones.
Cubre el service `appointment_status` (CRUD, guards is_initial/code/in_use, matriz).
El seed ya siembra 8 estados (SCHEDULED..RESCHEDULED) + su matriz.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_scheduling.helpers import auth_headers, build_bookable_scenario

PREFIX = "/api/v1/scheduling/appointment-statuses"


async def _new_status_payload(**overrides) -> dict:
    import uuid

    body = {
        "code": "TST_" + uuid.uuid4().hex[:8].upper(),
        "name": "Estado Test",
        "color": "#123456",
        "is_initial": False,
        "is_final": False,
        "is_active_attention": False,
        "display_order": 99,
    }
    body.update(overrides)
    return body


async def test_list_active_returns_seeded_statuses(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/active", headers=headers)
    assert r.status_code == 200, r.text
    codes = {s["code"] for s in r.json()}  # /active = lista cruda
    assert {"SCHEDULED", "CONFIRMED", "ATTENDED", "CANCELLED"} <= codes


async def test_list_paginated(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/list", json={"pagination": {"skip": 0, "limit": 50}}, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 8
    assert any(item["code"] == "SCHEDULED" for item in data["items"])


async def test_create_and_get_transitions(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    assert r.status_code == 201, r.text
    status_id = r.json()["data"]["id"]

    # Sin aristas configuradas al crear → matriz vacía.
    g = await client.get(f"{PREFIX}/{status_id}/transitions", headers=headers)
    assert g.status_code == 200, g.text
    assert g.json()["data"]["from_id"] == status_id
    assert g.json()["data"]["to"] == []


async def test_create_duplicate_code_409(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    payload = await _new_status_payload()
    r1 = await client.post(f"{PREFIX}", json=payload, headers=headers)
    assert r1.status_code == 201, r1.text
    r2 = await client.post(f"{PREFIX}", json=payload, headers=headers)
    assert r2.status_code == 409, r2.text
    assert r2.json()["code"] == "APPOINTMENT_STATUS_CODE_TAKEN"


async def test_create_second_initial_rejected_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    # SCHEDULED ya es is_initial (seed) → un segundo is_initial debe fallar.
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}", json=await _new_status_payload(is_initial=True), headers=headers
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "MULTIPLE_INITIAL_STATUS"


async def test_update_name_and_color(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    status_id = created.json()["data"]["id"]

    r = await client.put(
        f"{PREFIX}/{status_id}",
        json={"name": "Nuevo Nombre", "color": "#abcdef"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Nuevo Nombre"
    assert r.json()["data"]["color"] == "#abcdef"


async def test_update_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{PREFIX}/does-not-exist", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "APPOINTMENT_STATUS_NOT_FOUND"


async def test_update_turn_on_second_initial_rejected(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    status_id = created.json()["data"]["id"]
    # SCHEDULED ya es is_initial → encenderlo en otro estado debe fallar.
    r = await client.put(f"{PREFIX}/{status_id}", json={"is_initial": True}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "MULTIPLE_INITIAL_STATUS"


async def test_delete_status_success(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    status_id = created.json()["data"]["id"]
    r = await client.delete(f"{PREFIX}/{status_id}", headers=headers)
    assert r.status_code == 204, r.text
    # Ya no aparece en /active.
    active = await client.get(f"{PREFIX}/active", headers=headers)
    assert status_id not in {s["id"] for s in active.json()}


async def test_delete_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_set_transitions_replaces_edges(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    a = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    b = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    a_id, b_id = a.json()["data"]["id"], b.json()["data"]["id"]

    r = await client.put(
        f"{PREFIX}/{a_id}/transitions", json={"to_ids": [b_id]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()["data"]["to"]] == [b_id]

    # Reemplazo total por vacío.
    r2 = await client.put(f"{PREFIX}/{a_id}/transitions", json={"to_ids": []}, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["to"] == []


async def test_set_transitions_unknown_target_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    a = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    a_id = a.json()["data"]["id"]
    r = await client.put(
        f"{PREFIX}/{a_id}/transitions", json={"to_ids": ["ghost"]}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "APPOINTMENT_STATUS_NOT_FOUND"


async def test_set_transitions_self_loop_ignored(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    a = await client.post(f"{PREFIX}", json=await _new_status_payload(), headers=headers)
    a_id = a.json()["data"]["id"]
    # El service descarta la arista a sí mismo → matriz vacía resultante.
    r = await client.put(
        f"{PREFIX}/{a_id}/transitions", json={"to_ids": [a_id]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["to"] == []


async def test_transitions_not_found_status_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/ghost/transitions", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_status_in_use_409(client: AsyncClient, admin_credentials: dict) -> None:
    """Un estado referenciado por una cita viva no se puede borrar (SCHEDULED es el
    is_initial de toda cita nueva)."""
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
    scheduled_status_id = booked.json()["data"]["status"]["id"]

    r = await client.delete(f"{PREFIX}/{scheduled_status_id}", headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "APPOINTMENT_STATUS_IN_USE"
