"""Tests del timeline (LeadActivity): composer del asesor + feed + sistema."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_crm.conftest import (
    CRM,
    auth_headers,
    create_person,
    lead_status_options,
)


async def _create(client, headers, person_id, **body):
    return await client.post(
        f"{CRM}/persons/{person_id}/activities", json=body, headers=headers
    )


async def test_create_note_activity(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await _create(
        client, headers, person["id"], activity_type="NOTE", content="Primera nota"
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["activity_type"] == "NOTE"
    assert data["content"] == "Primera nota"


async def test_create_call_attempt_with_outcome(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await _create(
        client,
        headers,
        person["id"],
        activity_type="CALL_ATTEMPT",
        content="No contestó",
        outcome="no_answer",
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["outcome"] == "no_answer"


async def test_create_follow_up_requires_scheduled_for(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    # FOLLOW_UP_SCHEDULED sin scheduled_for → 422 (validator del schema).
    r = await _create(client, headers, person["id"], activity_type="FOLLOW_UP_SCHEDULED")
    assert r.status_code == 422, r.text


async def test_create_follow_up_scheduled(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await _create(
        client,
        headers,
        person["id"],
        activity_type="FOLLOW_UP_SCHEDULED",
        scheduled_for="2030-01-01T10:00:00+00:00",
    )
    assert r.status_code == 201, r.text


async def test_create_system_type_rejected_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    # STATUS_CHANGE no es un ADVISOR_ACTIVITY_TYPE → 422.
    r = await _create(client, headers, person["id"], activity_type="STATUS_CHANGE")
    assert r.status_code == 422, r.text


async def test_create_activity_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await _create(client, headers, "nope", activity_type="NOTE", content="x")
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


async def test_list_activities(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create(client, headers, person["id"], activity_type="NOTE", content="a")
    await _create(client, headers, person["id"], activity_type="NOTE", content="b")
    r = await client.post(
        f"{CRM}/persons/{person['id']}/activities/list", json={}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 2


async def test_list_activities_filtered_by_type(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    await _create(client, headers, person["id"], activity_type="NOTE", content="n")
    await _create(
        client, headers, person["id"], activity_type="CALL_ATTEMPT", content="c"
    )
    r = await client.post(
        f"{CRM}/persons/{person['id']}/activities/list",
        json={"activity_type": ["CALL_ATTEMPT"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert all(x["activity_type"] == "CALL_ATTEMPT" for x in rows)


async def test_list_activities_person_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CRM}/persons/nope/activities/list", json={}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_update_activity(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    created = (
        await _create(client, headers, person["id"], activity_type="NOTE", content="old")
    ).json()["data"]
    r = await client.put(
        f"{CRM}/persons/{person['id']}/activities/{created['id']}",
        json={"content": "nuevo contenido"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["content"] == "nuevo contenido"


async def test_update_activity_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.put(
        f"{CRM}/persons/{person['id']}/activities/nope",
        json={"content": "x"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "ACTIVITY_NOT_FOUND"


async def test_update_system_activity_rejected(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Un evento de sistema (STATUS_CHANGE, emitido al transicionar el lead) NO es
    editable por el asesor → 404 ACTIVITY_NOT_FOUND (audit trail inmutable)."""
    headers = await auth_headers(client, admin_credentials)
    opts = await lead_status_options(client, headers)
    person = await create_person(client, headers)
    await client.post(
        f"{CRM}/persons/{person['id']}/lead-status", json={}, headers=headers
    )
    await client.post(
        f"{CRM}/persons/{person['id']}/lead-status/transition",
        json={"to_lead_status_id": opts["INTENTANDO_CONTACTAR"]["id"]},
        headers=headers,
    )
    feed = await client.post(
        f"{CRM}/persons/{person['id']}/activities/list", json={}, headers=headers
    )
    system_acts = [
        a for a in feed.json()["data"] if a["activity_type"] == "STATUS_CHANGE"
    ]
    assert system_acts, "se esperaba un STATUS_CHANGE de sistema en el feed"
    r = await client.put(
        f"{CRM}/persons/{person['id']}/activities/{system_acts[0]['id']}",
        json={"content": "hack"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "ACTIVITY_NOT_FOUND"


async def test_delete_activity_recomputes_last_activity(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    # Lead activo → log toca last_activity_at.
    await client.post(
        f"{CRM}/persons/{person['id']}/lead-status", json={}, headers=headers
    )
    created = (
        await _create(client, headers, person["id"], activity_type="NOTE", content="x")
    ).json()["data"]
    r = await client.delete(
        f"{CRM}/persons/{person['id']}/activities/{created['id']}", headers=headers
    )
    assert r.status_code == 204, r.text
    # Ya no aparece en el feed (active=false).
    feed = await client.post(
        f"{CRM}/persons/{person['id']}/activities/list", json={}, headers=headers
    )
    note_ids = [a["id"] for a in feed.json()["data"] if a["activity_type"] == "NOTE"]
    assert created["id"] not in note_ids


async def test_delete_activity_not_found(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    person = await create_person(client, headers)
    r = await client.delete(
        f"{CRM}/persons/{person['id']}/activities/nope", headers=headers
    )
    assert r.status_code == 404, r.text
