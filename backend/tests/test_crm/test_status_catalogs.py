"""Tests del CRUD + matriz de transiciones de LeadStatus y CustomerStatus."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_crm.conftest import (
    CRM,
    auth_headers,
    customer_status_options,
    lead_status_options,
)

LS = f"{CRM}/lead-statuses"
CS = f"{CRM}/customer-statuses"


# ── LeadStatus ──────────────────────────────────────────────────────


async def test_list_active_lead_statuses_seeded(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    assert "NUEVO" in opts
    assert opts["NUEVO"]["is_initial"] is True
    assert opts["CITA_AGENDADA"]["is_won"] is True


async def test_list_lead_statuses_paginated(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{LS}/list", json={"pagination": {"skip": 0, "limit": 50}}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total"] >= 7


async def test_create_lead_status(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{LS}",
        json={"code": "PERDIDO_X", "name": "Perdido X", "color": "#000", "display_order": 99},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["code"] == "PERDIDO_X"


async def test_create_lead_status_duplicate_code(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{LS}", json={"code": "NUEVO", "name": "Repetido"}, headers=headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "LEAD_STATUS_CODE_TAKEN"


async def test_create_lead_status_won_requires_final(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{LS}",
        json={"code": "GANADO_BAD", "name": "Ganado", "is_won": True, "is_final": False},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "WON_REQUIRES_FINAL"


async def test_create_lead_status_multiple_initial(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    # Ya existe NUEVO como inicial → otro inicial debe fallar.
    r = await client.post(
        f"{LS}",
        json={"code": "OTRO_INICIAL", "name": "Otro inicial", "is_initial": True},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "MULTIPLE_INITIAL_STATUS"


async def test_update_lead_status(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = (
        await client.post(f"{LS}", json={"code": "UPD_LS", "name": "A"}, headers=headers)
    ).json()["data"]
    r = await client.put(
        f"{LS}/{created['id']}",
        json={"name": "Actualizado", "color": "", "display_order": 5},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Actualizado"
    assert data["color"] is None  # "" → None


async def test_update_lead_status_won_requires_final(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = (
        await client.post(f"{LS}", json={"code": "UPD_WON", "name": "A"}, headers=headers)
    ).json()["data"]
    r = await client.put(
        f"{LS}/{created['id']}", json={"is_won": True}, headers=headers
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "WON_REQUIRES_FINAL"


async def test_update_lead_status_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{LS}/nope", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "LEAD_STATUS_NOT_FOUND"


async def test_delete_lead_status(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = (
        await client.post(f"{LS}", json={"code": "DEL_LS", "name": "Borrar"}, headers=headers)
    ).json()["data"]
    r = await client.delete(f"{LS}/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text


async def test_delete_lead_status_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{LS}/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_lead_status_transitions_get_and_set(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    nuevo = opts["NUEVO"]["id"]
    contactado = opts["CONTACTADO"]["id"]
    interesado = opts["INTERESADO"]["id"]
    # GET (matriz seedeada): NUEVO va a INTENTANDO_CONTACTAR y NO_INTERESADO.
    r = await client.get(f"{LS}/{nuevo}/transitions", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["from_id"] == nuevo
    # PUT reemplaza las aristas de salida.
    r2 = await client.put(
        f"{LS}/{nuevo}/transitions",
        json={"to_ids": [contactado, interesado]},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    to_ids = {t["id"] for t in r2.json()["data"]["to"]}
    assert to_ids == {contactado, interesado}


async def test_set_transitions_unknown_target_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    nuevo = opts["NUEVO"]["id"]
    r = await client.put(
        f"{LS}/{nuevo}/transitions", json={"to_ids": ["ghost-id"]}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "LEAD_STATUS_NOT_FOUND"


async def test_get_transitions_status_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{LS}/nope/transitions", headers=headers)
    assert r.status_code == 404, r.text


# ── CustomerStatus ──────────────────────────────────────────────────


async def test_list_active_customer_statuses_seeded(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await customer_status_options(client, headers)
    assert opts["ACTIVO"]["is_initial"] is True
    assert opts["PERDIDO"]["is_final"] is True


async def test_customer_status_crud_and_matrix(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    # list paginated
    lp = await client.post(
        f"{CS}/list", json={"pagination": {"skip": 0, "limit": 50}}, headers=headers
    )
    assert lp.status_code == 200
    assert lp.json()["data"]["total"] >= 5
    # create
    created = await client.post(
        f"{CS}", json={"code": "CS_X", "name": "Cliente X"}, headers=headers
    )
    assert created.status_code == 201, created.text
    cid = created.json()["data"]["id"]
    # update (color "" → None)
    upd = await client.put(
        f"{CS}/{cid}", json={"name": "Cliente XX", "color": ""}, headers=headers
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["data"]["color"] is None
    # transitions
    opts = await customer_status_options(client, headers)
    activo = opts["ACTIVO"]["id"]
    g = await client.get(f"{CS}/{activo}/transitions", headers=headers)
    assert g.status_code == 200, g.text
    s = await client.put(
        f"{CS}/{activo}/transitions", json={"to_ids": [cid]}, headers=headers
    )
    assert s.status_code == 200, s.text
    assert {t["id"] for t in s.json()["data"]["to"]} == {cid}
    # delete
    d = await client.delete(f"{CS}/{cid}", headers=headers)
    assert d.status_code == 204, d.text


async def test_customer_status_duplicate_code(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CS}", json={"code": "ACTIVO", "name": "Dup"}, headers=headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CUSTOMER_STATUS_CODE_TAKEN"


async def test_customer_status_multiple_initial(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CS}",
        json={"code": "CS_INI", "name": "Otro inicial", "is_initial": True},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "MULTIPLE_INITIAL_STATUS"


async def test_customer_status_update_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{CS}/nope", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CUSTOMER_STATUS_NOT_FOUND"


async def test_customer_status_delete_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{CS}/nope", headers=headers)
    assert r.status_code == 404, r.text


async def test_customer_set_transitions_unknown_target(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await customer_status_options(client, headers)
    activo = opts["ACTIVO"]["id"]
    r = await client.put(
        f"{CS}/{activo}/transitions", json={"to_ids": ["ghost"]}, headers=headers
    )
    assert r.status_code == 404, r.text
