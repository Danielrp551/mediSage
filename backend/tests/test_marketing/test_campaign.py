"""
Tests de integración del service de Campaign (marketing).

Cubre create/list/get/update/transition/delete + M:N de promociones + casos de borde
(404, 409 duplicado, 400 validación de fechas/vertical/transición).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_marketing._helpers import (
    MARKETING,
    auth_headers,
    create_campaign,
    create_promotion,
    create_vertical,
    slug,
)

CAMPAIGNS = f"{MARKETING}/campaigns"


async def test_create_campaign_minimal(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    code = slug()
    r = await client.post(
        CAMPAIGNS,
        json={"code": code, "name": "Verano 2026", "start_date": "2026-01-01"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"] == code
    assert data["status"] == "draft"  # nace draft
    assert data["active"] is True
    assert data["promotions_count"] == 0
    assert data["promotions"] == []
    assert data["target_vertical_id"] is None


async def test_create_campaign_with_vertical(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    vertical_id = await create_vertical(client, headers)
    data = await create_campaign(client, headers, target_vertical_id=vertical_id)
    assert data["target_vertical_id"] == vertical_id
    assert data["target_vertical_name"] == "Vertical Test"
    assert data["target_vertical"]["id"] == vertical_id


async def test_create_campaign_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    code = slug()
    await create_campaign(client, headers, code=code)
    r = await client.post(
        CAMPAIGNS,
        json={"code": code, "name": "Otra", "start_date": "2026-01-01"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CAMPAIGN_CODE_TAKEN"


async def test_create_campaign_invalid_dates_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        CAMPAIGNS,
        json={
            "code": slug(),
            "name": "Mal",
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CAMPAIGN_INVALID_DATES"


async def test_create_campaign_unknown_vertical_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        CAMPAIGNS,
        json={
            "code": slug(),
            "name": "Sin vertical",
            "start_date": "2026-01-01",
            "target_vertical_id": "nope-does-not-exist",
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "TARGET_VERTICAL_NOT_FOUND"


async def test_create_campaign_invalid_code_slug_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        CAMPAIGNS,
        json={"code": "Bad Code!", "name": "X", "start_date": "2026-01-01"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_campaign_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CAMPAIGNS}/missing-id", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CAMPAIGN_NOT_FOUND"


async def test_get_campaign_ok(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    r = await client.get(f"{CAMPAIGNS}/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]


async def test_list_campaigns(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    r = await client.post(
        f"{CAMPAIGNS}/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 1
    assert created["id"] in [c["id"] for c in data["items"]]


async def test_list_active_campaigns(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    # `/active` solo devuelve campañas con status='active' (no draft) — hay que transicionar.
    tr = await client.post(
        f"{CAMPAIGNS}/{created['id']}/transition",
        json={"to_status": "active"},
        headers=headers,
    )
    assert tr.status_code == 200, tr.text
    r = await client.get(f"{CAMPAIGNS}/active", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()  # lista cruda, sin envelope
    assert isinstance(body, list)
    assert created["id"] in [c["id"] for c in body]


async def test_update_campaign(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    r = await client.put(
        f"{CAMPAIGNS}/{created['id']}",
        json={"name": "Nombre Nuevo", "description": "desc"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Nombre Nuevo"
    assert data["description"] == "desc"


async def test_update_campaign_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{CAMPAIGNS}/missing", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CAMPAIGN_NOT_FOUND"


async def test_update_campaign_invalid_dates_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers, start_date="2026-01-01")
    r = await client.put(
        f"{CAMPAIGNS}/{created['id']}",
        json={"end_date": "2025-01-01"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CAMPAIGN_INVALID_DATES"


async def test_update_campaign_unknown_vertical_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    r = await client.put(
        f"{CAMPAIGNS}/{created['id']}",
        json={"target_vertical_id": "nope"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "TARGET_VERTICAL_NOT_FOUND"


async def test_transition_campaign_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    # draft → active
    r = await client.post(
        f"{CAMPAIGNS}/{created['id']}/transition",
        json={"to_status": "active"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"
    # active → paused
    r = await client.post(
        f"{CAMPAIGNS}/{created['id']}/transition",
        json={"to_status": "paused"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "paused"


async def test_transition_campaign_not_allowed_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    # draft → paused NO permitido (draft solo → active)
    r = await client.post(
        f"{CAMPAIGNS}/{created['id']}/transition",
        json={"to_status": "paused"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CAMPAIGN_TRANSITION_NOT_ALLOWED"


async def test_transition_campaign_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CAMPAIGNS}/missing/transition",
        json={"to_status": "active"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CAMPAIGN_NOT_FOUND"


async def test_delete_campaign(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_campaign(client, headers)
    r = await client.delete(f"{CAMPAIGNS}/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # soft-delete → ya no se obtiene
    r = await client.get(f"{CAMPAIGNS}/{created['id']}", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_campaign_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{CAMPAIGNS}/missing", headers=headers)
    assert r.status_code == 404, r.text


# ── M:N de promociones ────────────────────────────────────────────────────────────────


async def test_set_and_get_campaign_promotions(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    campaign = await create_campaign(client, headers)
    promo1 = await create_promotion(client, headers)
    promo2 = await create_promotion(client, headers)

    r = await client.put(
        f"{CAMPAIGNS}/{campaign['id']}/promotions",
        json={"promotion_ids": [promo1["id"], promo2["id"]]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["promotions_count"] == 2
    assert {p["id"] for p in data["promotions"]} == {promo1["id"], promo2["id"]}

    # GET /promotions devuelve el M:N
    r = await client.get(f"{CAMPAIGNS}/{campaign['id']}/promotions", headers=headers)
    assert r.status_code == 200, r.text
    assert {p["id"] for p in r.json()["data"]} == {promo1["id"], promo2["id"]}

    # bulk-replace con lista vacía → limpia
    r = await client.put(
        f"{CAMPAIGNS}/{campaign['id']}/promotions",
        json={"promotion_ids": []},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["promotions_count"] == 0


async def test_set_campaign_promotions_unknown_promo_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    campaign = await create_campaign(client, headers)
    r = await client.put(
        f"{CAMPAIGNS}/{campaign['id']}/promotions",
        json={"promotion_ids": ["does-not-exist"]},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


async def test_set_campaign_promotions_campaign_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(
        f"{CAMPAIGNS}/missing/promotions",
        json={"promotion_ids": []},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CAMPAIGN_NOT_FOUND"


async def test_get_campaign_promotions_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CAMPAIGNS}/missing/promotions", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CAMPAIGN_NOT_FOUND"


async def test_set_campaign_promotions_duplicate_ids_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    campaign = await create_campaign(client, headers)
    promo = await create_promotion(client, headers)
    r = await client.put(
        f"{CAMPAIGNS}/{campaign['id']}/promotions",
        json={"promotion_ids": [promo["id"], promo["id"]]},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_campaign_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{CAMPAIGNS}/active")
    assert r.status_code == 401, r.text
