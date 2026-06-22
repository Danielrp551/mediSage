"""
Tests de integración del CRUD de Doctor (`/api/v1/staff/doctors`).

Cubren los happy paths del service `doctor` (create nested, get, list paginado,
list active con filtros, update parcial + reemplazo M:N, soft-delete) y los casos
de borde: 404, 409 (email tomado), 400 (sede/vertical inexistente, ids
duplicados), y el contrato `generated_password`.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_staff.helpers import (
    admin_headers,
    create_branch,
    create_doctor,
    create_office,
    create_vertical,
)

STAFF = "/api/v1/staff"


async def test_create_doctor_genera_password(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    body = await create_doctor(client, headers)
    assert body["success"] is True
    assert body["generated_password"], "sin password en el payload, el service debe generar una"
    data = body["data"]
    assert data["id"]
    assert data["user_id"]
    assert data["slot_duration_min"] == 30
    assert data["active"] is True
    assert data["branches_count"] == 0
    assert data["verticals_count"] == 0


async def test_create_doctor_con_password_no_devuelve_generada(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    body = await create_doctor(client, headers, password="SuperSecret123")
    assert body["generated_password"] is None


async def test_create_doctor_con_sedes_y_verticales(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    branch_id = await create_branch(client, headers)
    vertical_id = await create_vertical(client, headers)
    body = await create_doctor(
        client, headers, branch_ids=[branch_id], vertical_ids=[vertical_id]
    )
    data = body["data"]
    assert data["branches_count"] == 1
    assert data["verticals_count"] == 1
    assert [b["id"] for b in data["branches"]] == [branch_id]
    assert [v["id"] for v in data["verticals"]] == [vertical_id]


async def test_create_doctor_email_duplicado_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    email = "dup_doctor@example.com"
    await create_doctor(client, headers, email=email)
    r = await client.post(
        f"{STAFF}/doctors",
        json={"user": {"email": email, "first_name": "Otro", "last_name": "Doc"}},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "EMAIL_TAKEN"


async def test_create_doctor_sede_inexistente_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.post(
        f"{STAFF}/doctors",
        json={
            "user": {"email": "noborder@example.com", "first_name": "X", "last_name": "Y"},
            "branch_ids": ["does-not-exist"],
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "BRANCH_NOT_FOUND"


async def test_create_doctor_vertical_inexistente_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.post(
        f"{STAFF}/doctors",
        json={
            "user": {"email": "novert@example.com", "first_name": "X", "last_name": "Y"},
            "vertical_ids": ["nope"],
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "VERTICAL_NOT_FOUND"


async def test_create_doctor_ids_duplicados_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.post(
        f"{STAFF}/doctors",
        json={
            "user": {"email": "dupids@example.com", "first_name": "X", "last_name": "Y"},
            "branch_ids": ["same", "same"],
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_doctor_ok(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    created = (await create_doctor(client, headers))["data"]
    r = await client.get(f"{STAFF}/doctors/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == created["id"]
    assert data["user"]["email"] == created["email"]
    assert data["branches"] == []
    assert data["verticals"] == []


async def test_get_doctor_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.get(f"{STAFF}/doctors/missing-id", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "DOCTOR_NOT_FOUND"


async def test_list_doctors_paginado(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    branch_id = await create_branch(client, headers)
    await create_doctor(client, headers, branch_ids=[branch_id])
    await create_doctor(client, headers)
    r = await client.post(
        f"{STAFF}/doctors/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    item = data["items"][0]
    assert "full_name" in item
    assert "email" in item
    assert "branches_count" in item
    assert "verticals_count" in item


async def test_list_doctors_filtra_por_cmp_code(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    # cmp_code es un ALLOWED_FIELD del repositorio → filtrable.
    n_email = "withcmp@example.com"
    r = await client.post(
        f"{STAFF}/doctors",
        json={
            "user": {"email": n_email, "first_name": "Cmp", "last_name": "Doc"},
            "cmp_code": "CMP-UNIQ-999",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"{STAFF}/doctors/list",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "filters": {
                "filters": [
                    {
                        "operator": "AND",
                        "conditions": [
                            {"field": "cmp_code", "operator": "eq", "value": "CMP-UNIQ-999"}
                        ],
                    }
                ]
            },
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["cmp_code"] == "CMP-UNIQ-999"


async def test_list_active_doctors_y_filtros(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    branch_id = await create_branch(client, headers)
    vertical_id = await create_vertical(client, headers)
    assigned = (
        await create_doctor(
            client, headers, branch_ids=[branch_id], vertical_ids=[vertical_id]
        )
    )["data"]
    # Otro doctor sin sede/vertical.
    await create_doctor(client, headers)

    # /active devuelve una lista CRUDA (sin envelope).
    r = await client.get(f"{STAFF}/doctors/active", headers=headers)
    assert r.status_code == 200, r.text
    options = r.json()
    assert isinstance(options, list)
    assert assigned["id"] in [o["id"] for o in options]

    # Filtrar por sede acota al doctor asignado.
    r = await client.get(f"{STAFF}/doctors/active?branch_id={branch_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert [o["id"] for o in r.json()] == [assigned["id"]]

    # Filtrar por vertical idem.
    r = await client.get(
        f"{STAFF}/doctors/active?vertical_id={vertical_id}", headers=headers
    )
    assert r.status_code == 200, r.text
    assert [o["id"] for o in r.json()] == [assigned["id"]]


async def test_update_doctor_campos_y_mn(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    branch_id = await create_branch(client, headers)
    vertical_id = await create_vertical(client, headers)
    created = (await create_doctor(client, headers))["data"]

    r = await client.put(
        f"{STAFF}/doctors/{created['id']}",
        json={
            "cmp_code": "CMP-12345",
            "bio": "Cardiólogo con 10 años de experiencia",
            "slot_duration_min": 45,
            "branch_ids": [branch_id],
            "vertical_ids": [vertical_id],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["cmp_code"] == "CMP-12345"
    assert data["bio"] == "Cardiólogo con 10 años de experiencia"
    assert data["slot_duration_min"] == 45
    assert data["branches_count"] == 1
    assert data["verticals_count"] == 1


async def test_update_doctor_reemplaza_mn_total(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    b1 = await create_branch(client, headers)
    b2 = await create_branch(client, headers)
    created = (await create_doctor(client, headers, branch_ids=[b1]))["data"]

    # Reemplazo total: branch_ids=[b2] elimina b1.
    r = await client.put(
        f"{STAFF}/doctors/{created['id']}",
        json={"branch_ids": [b2]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert [b["id"] for b in data["branches"]] == [b2]


async def test_update_doctor_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.put(
        f"{STAFF}/doctors/nope", json={"cmp_code": "X"}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "DOCTOR_NOT_FOUND"


async def test_update_doctor_sede_inexistente_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await admin_headers(client, admin_credentials)
    created = (await create_doctor(client, headers))["data"]
    r = await client.put(
        f"{STAFF}/doctors/{created['id']}",
        json={"branch_ids": ["ghost"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "BRANCH_NOT_FOUND"


async def test_delete_doctor_soft(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    created = (await create_doctor(client, headers))["data"]
    r = await client.delete(f"{STAFF}/doctors/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # Tras el soft-delete el get da 404 (BaseRepository filtra deleted_at).
    r = await client.get(f"{STAFF}/doctors/{created['id']}", headers=headers)
    assert r.status_code == 404, r.text
    # Y ya no aparece en /active.
    r = await client.get(f"{STAFF}/doctors/active", headers=headers)
    assert created["id"] not in [o["id"] for o in r.json()]


async def test_delete_doctor_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await admin_headers(client, admin_credentials)
    r = await client.delete(f"{STAFF}/doctors/ghost", headers=headers)
    assert r.status_code == 404, r.text


async def test_doctor_endpoints_require_auth(client: AsyncClient) -> None:
    r = await client.post(f"{STAFF}/doctors/list", json={"pagination": {"skip": 0, "limit": 10}})
    assert r.status_code == 401
