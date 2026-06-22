"""
Tests del ciclo de vida lead/cliente: crear lead, transicionar (matriz F2),
historial, promote-to-customer + delete-guards de los catálogos en uso (F4).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_crm.conftest import (
    CRM,
    auth_headers,
    create_person,
    customer_status_options,
    lead_status_options,
)


async def _create_lead(client, headers, person_id, **body):
    r = await client.post(
        f"{CRM}/persons/{person_id}/lead-status", json=body, headers=headers
    )
    return r


# ── Lead lifecycle ──────────────────────────────────────────────────


async def test_get_lead_status_none(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.get(f"{CRM}/persons/{person['id']}/lead-status", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None


async def test_get_lead_status_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CRM}/persons/nope/lead-status", headers=headers)
    assert r.status_code == 404, r.text


async def test_create_lead_status(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await _create_lead(client, headers, person["id"], reason="Inbound")
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["lead_status"]["code"] == "NUEVO"
    assert data["person_id"] == person["id"]


async def test_create_lead_status_already_active(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    r = await _create_lead(client, headers, person["id"])
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "ALREADY_HAS_ACTIVE_LEAD"


async def test_create_lead_status_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await _create_lead(client, headers, "nope")
    assert r.status_code == 404, r.text


async def test_transition_lead_status(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    # NUEVO → INTENTANDO_CONTACTAR (arista válida de la matriz seedeada).
    r = await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": opts["INTENTANDO_CONTACTAR"]["id"], "reason": "Llamada 1"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lead_status"]["code"] == "INTENTANDO_CONTACTAR"


async def test_transition_lead_not_allowed(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    # NUEVO → CONTACTADO no es una arista válida.
    r = await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": opts["CONTACTADO"]["id"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "LEAD_TRANSITION_NOT_ALLOWED"


async def test_transition_lead_no_active(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    r = await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": opts["CONTACTADO"]["id"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "NO_ACTIVE_LEAD"


async def test_transition_lead_target_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    r = await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": "ghost"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "LEAD_STATUS_NOT_FOUND"


async def test_transition_lead_to_final_closes_lead(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    # NUEVO → NO_INTERESADO (final) cierra el lead → data=null.
    r = await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": opts["NO_INTERESADO"]["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None
    # Y ya no hay lead activo.
    cur = await client.get(f"{CRM}/persons/{person['id']}/lead-status", headers=headers)
    assert cur.json()["data"] is None


async def test_lead_status_history(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"], reason="Alta")
    await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": opts["INTENTANDO_CONTACTAR"]["id"]},
        headers=headers,
    )
    r = await client.get(
        f"{CRM}/persons/{person['id']}/lead-status/history", headers=headers
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 2
    # La fila de creación tiene from_lead_status null.
    creation = [x for x in rows if x["from_lead_status"] is None]
    assert creation and creation[0]["to_lead_status"]["code"] == "NUEVO"


async def test_lead_history_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CRM}/persons/nope/lead-status/history", headers=headers)
    assert r.status_code == 404, r.text


# ── Promote to customer + customer lifecycle ────────────────────────


async def test_promote_to_customer(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    r = await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer",
        json={"reason": "Cerró"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["customer_status"]["code"] == "ACTIVO"


async def test_promote_already_customer(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    r = await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "ALREADY_CUSTOMER"


async def test_promote_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CRM}/persons/nope/promote-to-customer", json={}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_promote_closes_won_lead_when_reachable(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Si el lead está en EVALUANDO (puede llegar a CITA_AGENDADA, que es is_won),
    promover lo cierra como ganado."""
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    # Camino NUEVO → INTENTANDO_CONTACTAR → CONTACTADO → INTERESADO → EVALUANDO.
    for code in ["INTENTANDO_CONTACTAR", "CONTACTADO", "INTERESADO", "EVALUANDO"]:
        tr = await client.post(
            f"{CRM}/persons/{person['id']}/lead-status/transition",
            json={"to_lead_status_id": opts[code]["id"]},
            headers=headers,
        )
        assert tr.status_code == 200, tr.text
    r = await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    assert r.status_code == 201, r.text
    # El lead se cerró como ganado.
    lead = await client.get(
        f"{CRM}/persons/{person['id']}/lead-status", headers=headers
    )
    assert lead.json()["data"] is None


async def test_customer_transition(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await customer_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    # ACTIVO → EN_TRATAMIENTO (arista válida).
    r = await client.post(
        f"{CRM}/persons/{person['id']}/customer-status/transition",
        json={"to_customer_status_id": opts["EN_TRATAMIENTO"]["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["customer_status"]["code"] == "EN_TRATAMIENTO"


async def test_customer_transition_not_allowed(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    # ACTIVO → COMPLETADO está permitido; usar una NO permitida: PERDIDO→ACTIVO no aplica.
    # COMPLETADO no es alcanzable directo? sí lo es. Usar EN_TRATAMIENTO→... no.
    # Forzar una no permitida: primero ir a PERDIDO (final) cerraría. Usar arista inexistente:
    # ACTIVO no transiciona a sí mismo (defensivo) ni a un destino sin arista.
    # COMPLETADO -> está permitido. Probamos ACTIVO -> (un estado sin arista): creamos uno.
    new_cs = (
        await client.post(
            f"{CRM}/customer-statuses",
            json={"code": "AISLADO", "name": "Aislado"},
            headers=headers,
        )
    ).json()["data"]
    r = await client.post(
        f"{CRM}/persons/{person['id']}/customer-status/transition",
        json={"to_customer_status_id": new_cs["id"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CUSTOMER_TRANSITION_NOT_ALLOWED"


async def test_customer_transition_to_final_closes(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await customer_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    # ACTIVO → PERDIDO (final) cierra el cliente.
    r = await client.post(
        f"{CRM}/persons/{person['id']}/customer-status/transition",
        json={"to_customer_status_id": opts["PERDIDO"]["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None


async def test_customer_transition_not_a_customer(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await customer_status_options(client, headers)
    person = await create_person(client, headers)
    r = await client.post(
        f"{CRM}/persons/{person['id']}/customer-status/transition",
        json={"to_customer_status_id": opts["EN_TRATAMIENTO"]["id"]},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "NOT_A_CUSTOMER"


async def test_customer_transition_target_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    r = await client.post(
        f"{CRM}/persons/{person['id']}/customer-status/transition",
        json={"to_customer_status_id": "ghost"},
        headers=headers,
    )
    assert r.status_code == 404, r.text


async def test_get_customer_status_none_and_history(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.get(
        f"{CRM}/persons/{person['id']}/customer-status", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None
    # Promover y revisar el historial.
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    h = await client.get(
        f"{CRM}/persons/{person['id']}/customer-status/history", headers=headers
    )
    assert h.status_code == 200, h.text
    rows = h.json()["data"]
    assert rows and rows[0]["to_customer_status"]["code"] == "ACTIVO"


async def test_customer_status_history_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(
        f"{CRM}/persons/nope/customer-status/history", headers=headers
    )
    assert r.status_code == 404, r.text


# ── Delete-guards de catálogos en uso (F4) ──────────────────────────


async def test_delete_lead_status_in_use_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])  # usa NUEVO
    r = await client.delete(f"{CRM}/lead-statuses/{opts['NUEVO']['id']}", headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "LEAD_STATUS_IN_USE"


async def test_delete_customer_status_in_use_conflicts(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    opts = await customer_status_options(client, headers)
    person = await create_person(client, headers)
    await _create_lead(client, headers, person["id"])
    await client.post(
        f"{CRM}/persons/{person['id']}/promote-to-customer", json={}, headers=headers
    )
    r = await client.delete(
        f"{CRM}/customer-statuses/{opts['ACTIVO']['id']}", headers=headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CUSTOMER_STATUS_IN_USE"
