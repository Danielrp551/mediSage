"""
Tests de integración de la disponibilidad del doctor
(`/api/v1/staff/doctors/{id}/availability`).

Cubren el service `doctor_availability`: alta masiva (bulk), list con/sin rango,
update (mover/redimensionar) y delete, más los tres invariantes cross-tabla:
OFFICE_NOT_IN_BRANCH, DOCTOR_NOT_IN_BRANCH y AVAILABILITY_OVERLAP, y el
AVAILABILITY_INVALID_RANGE del PUT parcial.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_staff.helpers import (
    admin_headers,
    create_branch,
    create_doctor,
    create_office,
)

STAFF = "/api/v1/staff"


async def _setup_doctor_with_branch_office(client: AsyncClient, headers: dict) -> dict:
    """Devuelve {doctor_id, branch_id, office_id} con el doctor asignado a la sede
    (requisito del invariante DOCTOR_NOT_IN_BRANCH)."""
    branch_id = await create_branch(client, headers)
    office_id = await create_office(client, headers, branch_id)
    doctor = (await create_doctor(client, headers, branch_ids=[branch_id]))["data"]
    return {"doctor_id": doctor["id"], "branch_id": branch_id, "office_id": office_id}


def _block(ctx: dict, *, date: str, opens: str, closes: str) -> dict:
    return {
        "branch_id": ctx["branch_id"],
        "office_id": ctx["office_id"],
        "date": date,
        "opens_at": opens,
        "closes_at": closes,
    }


async def test_bulk_create_y_list(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    r = await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                _block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00"),
                _block(ctx, date="2026-07-01", opens="14:00:00", closes="18:00:00"),
            ]
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    items = r.json()["data"]
    assert len(items) == 2
    first = items[0]
    assert first["doctor_id"] == ctx["doctor_id"]
    assert first["branch_name"]  # denormalizado
    assert first["office_code"]  # denormalizado
    assert first["office_name"]  # denormalizado

    # List sin filtro devuelve los 2.
    r = await client.get(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability", headers=headers
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 2


async def test_list_con_rango_de_fechas(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                _block(ctx, date="2026-07-01", opens="08:00:00", closes="12:00:00"),
                _block(ctx, date="2026-07-10", opens="08:00:00", closes="12:00:00"),
            ]
        },
        headers=headers,
    )
    r = await client.get(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability?from=2026-07-01&to=2026-07-05",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["date"] == "2026-07-01"


async def test_bulk_overlap_dentro_del_body_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    r = await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                _block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00"),
                _block(ctx, date="2026-07-01", opens="12:00:00", closes="18:00:00"),
            ]
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "AVAILABILITY_OVERLAP"


async def test_bulk_overlap_con_existente_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={"blocks": [_block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00")]},
        headers=headers,
    )
    r = await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={"blocks": [_block(ctx, date="2026-07-01", opens="10:00:00", closes="11:00:00")]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "AVAILABILITY_OVERLAP"


async def test_bloques_adyacentes_ok(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    # [08-13) y [13-20) son adyacentes, half-open → NO se solapan.
    r = await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                _block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00"),
                _block(ctx, date="2026-07-01", opens="13:00:00", closes="20:00:00"),
            ]
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["data"]) == 2


async def test_office_no_pertenece_a_branch_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    # Office de OTRA sede (a la que el doctor también está asignado, para aislar el
    # invariante 1 del 2).
    other_branch = await create_branch(client, headers)
    other_office = await create_office(client, headers, other_branch)
    await client.put(
        f"{STAFF}/doctors/{ctx['doctor_id']}",
        json={"branch_ids": [ctx["branch_id"], other_branch]},
        headers=headers,
    )
    r = await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                {
                    "branch_id": ctx["branch_id"],
                    "office_id": other_office,  # office de otra sede
                    "date": "2026-07-01",
                    "opens_at": "08:00:00",
                    "closes_at": "13:00:00",
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "OFFICE_NOT_IN_BRANCH"


async def test_doctor_no_asignado_a_branch_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    # Doctor SIN sedes asignadas.
    branch_id = await create_branch(client, headers)
    office_id = await create_office(client, headers, branch_id)
    doctor = (await create_doctor(client, headers))["data"]
    r = await client.post(
        f"{STAFF}/doctors/{doctor['id']}/availability",
        json={
            "blocks": [
                {
                    "branch_id": branch_id,
                    "office_id": office_id,
                    "date": "2026-07-01",
                    "opens_at": "08:00:00",
                    "closes_at": "13:00:00",
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "DOCTOR_NOT_IN_BRANCH"


async def test_bulk_doctor_inexistente_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.post(
        f"{STAFF}/doctors/ghost/availability",
        json={
            "blocks": [
                {
                    "branch_id": "b",
                    "office_id": "o",
                    "date": "2026-07-01",
                    "opens_at": "08:00:00",
                    "closes_at": "13:00:00",
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "DOCTOR_NOT_FOUND"


async def test_list_doctor_inexistente_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.get(f"{STAFF}/doctors/ghost/availability", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "DOCTOR_NOT_FOUND"


async def test_create_block_rango_invalido_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    # closes <= opens → el validator de Pydantic (ambos lados presentes) da 422.
    r = await client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={"blocks": [_block(ctx, date="2026-07-01", opens="18:00:00", closes="08:00:00")]},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_update_block_mover(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    created = (
        await client.post(
            f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
            json={"blocks": [_block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00")]},
            headers=headers,
        )
    ).json()["data"][0]
    r = await client.put(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability/{created['id']}",
        json={"opens_at": "09:00:00", "closes_at": "12:00:00"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["opens_at"] == "09:00:00"
    assert data["closes_at"] == "12:00:00"


async def test_update_block_rango_invalido_parcial_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    created = (
        await client.post(
            f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
            json={"blocks": [_block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00")]},
            headers=headers,
        )
    ).json()["data"][0]
    # Solo movemos opens_at más tarde que el closes existente → merged inválido →
    # AVAILABILITY_INVALID_RANGE (el validator cross-field no corre con un solo lado).
    r = await client.put(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability/{created['id']}",
        json={"opens_at": "20:00:00"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "AVAILABILITY_INVALID_RANGE"


async def test_update_block_overlap_400(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    blocks = (
        await client.post(
            f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
            json={
                "blocks": [
                    _block(ctx, date="2026-07-01", opens="08:00:00", closes="12:00:00"),
                    _block(ctx, date="2026-07-01", opens="14:00:00", closes="18:00:00"),
                ]
            },
            headers=headers,
        )
    ).json()["data"]
    # Extender el primer bloque para que pise el segundo.
    r = await client.put(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability/{blocks[0]['id']}",
        json={"closes_at": "15:00:00"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "AVAILABILITY_OVERLAP"


async def test_update_block_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    r = await client.put(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability/ghost",
        json={"opens_at": "09:00:00"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "AVAILABILITY_NOT_FOUND"


async def test_update_block_ownership_de_otro_doctor_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    other_doctor = (await create_doctor(client, headers))["data"]
    created = (
        await client.post(
            f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
            json={"blocks": [_block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00")]},
            headers=headers,
        )
    ).json()["data"][0]
    # El bloque existe pero pertenece a otro doctor → 404 (ownership).
    r = await client.put(
        f"{STAFF}/doctors/{other_doctor['id']}/availability/{created['id']}",
        json={"opens_at": "09:00:00"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "AVAILABILITY_NOT_FOUND"


async def test_delete_block(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    created = (
        await client.post(
            f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
            json={"blocks": [_block(ctx, date="2026-07-01", opens="08:00:00", closes="13:00:00")]},
            headers=headers,
        )
    ).json()["data"][0]
    r = await client.delete(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability/{created['id']}", headers=headers
    )
    assert r.status_code == 204, r.text
    # Ya no aparece en el list.
    r = await client.get(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability", headers=headers
    )
    assert r.json()["data"] == []


async def test_delete_block_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    ctx = await _setup_doctor_with_branch_office(client, headers)
    r = await client.delete(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability/ghost", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "AVAILABILITY_NOT_FOUND"
