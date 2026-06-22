"""
Tests de integración del service `office_closure` (excepciones de calendario).

CRUD individual: create / list (filtrable por rango) / delete (sin update).
Cubre happy paths + casos de borde: office inexistente (404), validación 422
(ends <= starts), filtro por rango, ownership al borrar (404 si el closure
pertenece a otro office), y delete inexistente (404).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_clinic.conftest import (
    CLINIC,
    auth_headers,
    create_branch,
    create_office,
)


async def _office_id(client: AsyncClient, headers: dict, code: str = "c-01") -> str:
    # Branch codes are strict lowercase slugs (no hyphens); office codes are
    # looser (hyphens allowed). Derive a slug-safe branch code from `code`.
    branch_code = "sede_" + code.replace("-", "_")
    branch = await create_branch(client, headers, code=branch_code)
    office = await create_office(client, headers, branch["id"], code=code)
    return office["id"]


def _closure_payload(**overrides: object) -> dict:
    payload: dict = {
        "starts_at": "2026-12-24T00:00:00+00:00",
        "ends_at": "2026-12-26T00:00:00+00:00",
        "is_closed": True,
        "reason": "Navidad",
    }
    payload.update(overrides)
    return payload


async def test_create_closure_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.post(
        f"{CLINIC}/offices/{office_id}/closures", json=_closure_payload(), headers=headers
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["office_id"] == office_id
    assert data["reason"] == "Navidad"
    assert data["is_closed"] is True
    assert data["created_by_user"]["email"] == admin_credentials["email"]


async def test_create_closure_office_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CLINIC}/offices/ghost/closures", json=_closure_payload(), headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "OFFICE_NOT_FOUND"


async def test_create_closure_ends_before_starts_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.post(
        f"{CLINIC}/offices/{office_id}/closures",
        json=_closure_payload(
            starts_at="2026-12-26T00:00:00+00:00", ends_at="2026-12-24T00:00:00+00:00"
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_create_closure_empty_reason_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.post(
        f"{CLINIC}/offices/{office_id}/closures",
        json=_closure_payload(reason=""),
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_list_closures_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    await client.post(
        f"{CLINIC}/offices/{office_id}/closures", json=_closure_payload(), headers=headers
    )
    r = await client.get(f"{CLINIC}/offices/{office_id}/closures", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["reason"] == "Navidad"


async def test_list_closures_office_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CLINIC}/offices/ghost/closures", headers=headers)
    assert r.status_code == 404, r.text


async def test_list_closures_range_filter(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    # December closure.
    await client.post(
        f"{CLINIC}/offices/{office_id}/closures",
        json=_closure_payload(
            starts_at="2026-12-24T00:00:00+00:00",
            ends_at="2026-12-26T00:00:00+00:00",
            reason="Navidad",
        ),
        headers=headers,
    )
    # January closure.
    await client.post(
        f"{CLINIC}/offices/{office_id}/closures",
        json=_closure_payload(
            starts_at="2027-01-01T00:00:00+00:00",
            ends_at="2027-01-02T00:00:00+00:00",
            reason="Anho Nuevo",
        ),
        headers=headers,
    )
    # Filter to the December window only.
    r = await client.get(
        f"{CLINIC}/offices/{office_id}/closures",
        params={"from": "2026-12-01T00:00:00+00:00", "to": "2026-12-31T00:00:00+00:00"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    reasons = {c["reason"] for c in r.json()["data"]}
    assert "Navidad" in reasons
    assert "Anho Nuevo" not in reasons


async def test_delete_closure_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    created = await client.post(
        f"{CLINIC}/offices/{office_id}/closures", json=_closure_payload(), headers=headers
    )
    closure_id = created.json()["data"]["id"]
    r = await client.delete(
        f"{CLINIC}/offices/{office_id}/closures/{closure_id}", headers=headers
    )
    assert r.status_code == 204, r.text
    # Gone from the list.
    listed = await client.get(f"{CLINIC}/offices/{office_id}/closures", headers=headers)
    assert listed.json()["data"] == []


async def test_delete_closure_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_id = await _office_id(client, headers)
    r = await client.delete(
        f"{CLINIC}/offices/{office_id}/closures/ghost", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CLOSURE_NOT_FOUND"


async def test_delete_closure_wrong_office_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    office_a = await _office_id(client, headers, code="c-a")
    office_b = await _office_id(client, headers, code="c-b")
    created = await client.post(
        f"{CLINIC}/offices/{office_a}/closures", json=_closure_payload(), headers=headers
    )
    closure_id = created.json()["data"]["id"]
    # Trying to delete office_a's closure through office_b must 404 (ownership check).
    r = await client.delete(
        f"{CLINIC}/offices/{office_b}/closures/{closure_id}", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CLOSURE_NOT_FOUND"
