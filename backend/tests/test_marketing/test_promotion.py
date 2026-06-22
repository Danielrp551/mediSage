"""
Tests de integración del service de Promotion (marketing).

Cubre create/list/get/update/delete + M:N de productos + usage-summary + validación del
descuento en el service (_validate_discount) + casos de borde (404, 409, 400).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_marketing._helpers import (
    MARKETING,
    auth_headers,
    create_full_product,
    create_promotion,
    create_vertical,  # noqa: F401  (kept for clarity / parity)
    slug,
)

PROMOTIONS = f"{MARKETING}/promotions"


async def test_create_promotion_percentage(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    code = slug()
    r = await client.post(
        PROMOTIONS,
        json={
            "code": code,
            "name": "10% off",
            "discount_type": "percentage",
            "discount_value": "10.00",
            "currency": "PEN",
            "start_date": "2026-01-01",
            "applies_to_all_products": True,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"] == code
    assert data["discount_type"] == "percentage"
    assert data["applies_to_all_products"] is True
    assert data["products_count"] == 0
    assert data["total_uses"] == 0


async def test_create_promotion_fixed_amount(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    data = await create_promotion(
        client, headers, discount_type="fixed_amount", discount_value="25.50"
    )
    assert data["discount_type"] == "fixed_amount"


async def test_create_promotion_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    code = slug()
    await create_promotion(client, headers, code=code)
    r = await client.post(
        PROMOTIONS,
        json={
            "code": code,
            "name": "Dup",
            "discount_type": "percentage",
            "discount_value": "5.00",
            "start_date": "2026-01-01",
            "applies_to_all_products": True,
        },
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PROMOTION_CODE_TAKEN"


async def test_create_promotion_percentage_out_of_range_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        PROMOTIONS,
        json={
            "code": slug(),
            "name": "Bad pct",
            "discount_type": "percentage",
            "discount_value": "150.00",
            "start_date": "2026-01-01",
            "applies_to_all_products": True,
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DISCOUNT"


async def test_create_promotion_fixed_amount_zero_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        PROMOTIONS,
        json={
            "code": slug(),
            "name": "Zero",
            "discount_type": "fixed_amount",
            "discount_value": "0.00",
            "start_date": "2026-01-01",
            "applies_to_all_products": True,
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DISCOUNT"


async def test_create_promotion_invalid_dates_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        PROMOTIONS,
        json={
            "code": slug(),
            "name": "Bad dates",
            "discount_type": "percentage",
            "discount_value": "10.00",
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
            "applies_to_all_products": True,
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DATES"


async def test_create_promotion_invalid_currency_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        PROMOTIONS,
        json={
            "code": slug(),
            "name": "Bad cur",
            "discount_type": "percentage",
            "discount_value": "10.00",
            "currency": "pen",
            "start_date": "2026-01-01",
            "applies_to_all_products": True,
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_get_promotion_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{PROMOTIONS}/missing", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


async def test_get_promotion_ok(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.get(f"{PROMOTIONS}/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]


async def test_list_promotions(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.post(
        f"{PROMOTIONS}/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert created["id"] in [p["id"] for p in data["items"]]


async def test_list_active_promotions(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.get(f"{PROMOTIONS}/active", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()  # lista cruda
    assert isinstance(body, list)
    assert created["id"] in [p["id"] for p in body]


async def test_update_promotion(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.put(
        f"{PROMOTIONS}/{created['id']}",
        json={"name": "Promo Renombrada", "discount_value": "20.00"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Promo Renombrada"
    assert data["discount_value"] == "20.00"


async def test_update_promotion_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(f"{PROMOTIONS}/missing", json={"name": "X"}, headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


async def test_update_promotion_discount_out_of_range_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers, discount_type="percentage")
    r = await client.put(
        f"{PROMOTIONS}/{created['id']}",
        json={"discount_value": "200.00"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DISCOUNT"


async def test_update_promotion_null_discount_value_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.put(
        f"{PROMOTIONS}/{created['id']}",
        json={"discount_value": None},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DISCOUNT"


async def test_update_promotion_null_currency_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.put(
        f"{PROMOTIONS}/{created['id']}",
        json={"currency": None},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DISCOUNT"


async def test_update_promotion_invalid_dates_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers, start_date="2026-01-01")
    r = await client.put(
        f"{PROMOTIONS}/{created['id']}",
        json={"end_date": "2025-01-01"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_INVALID_DATES"


async def test_delete_promotion(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    created = await create_promotion(client, headers)
    r = await client.delete(f"{PROMOTIONS}/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    r = await client.get(f"{PROMOTIONS}/{created['id']}", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_promotion_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.delete(f"{PROMOTIONS}/missing", headers=headers)
    assert r.status_code == 404, r.text


# ── M:N de productos ──────────────────────────────────────────────────────────────────


async def test_set_and_get_promotion_products(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    promo = await create_promotion(client, headers, applies_to_all_products=False)
    product_id = await create_full_product(client, headers)

    r = await client.put(
        f"{PROMOTIONS}/{promo['id']}/products",
        json={"product_ids": [product_id]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["products_count"] == 1
    assert product_id in [p["id"] for p in data["products"]]

    r = await client.get(f"{PROMOTIONS}/{promo['id']}/products", headers=headers)
    assert r.status_code == 200, r.text
    assert product_id in [p["id"] for p in r.json()["data"]]


async def test_set_promotion_products_unknown_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    promo = await create_promotion(client, headers, applies_to_all_products=False)
    r = await client.put(
        f"{PROMOTIONS}/{promo['id']}/products",
        json={"product_ids": ["does-not-exist"]},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_set_promotion_products_promo_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.put(
        f"{PROMOTIONS}/missing/products",
        json={"product_ids": []},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


async def test_get_promotion_products_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{PROMOTIONS}/missing/products", headers=headers)
    assert r.status_code == 404, r.text


async def test_promotion_applies_to_all_ignores_products(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Con applies_to_all_products=true el M:N de productos se ignora → count=0."""
    headers = await auth_headers(client, admin_credentials)
    promo = await create_promotion(client, headers, applies_to_all_products=True)
    product_id = await create_full_product(client, headers)
    r = await client.put(
        f"{PROMOTIONS}/{promo['id']}/products",
        json={"product_ids": [product_id]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    # products_count se reporta 0 cuando applies_to_all_products
    assert r.json()["data"]["products_count"] == 0


# ── usage-summary ─────────────────────────────────────────────────────────────────────


async def test_usage_summary_empty(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    promo = await create_promotion(client, headers)
    r = await client.get(f"{PROMOTIONS}/{promo['id']}/usage-summary", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["promotion_id"] == promo["id"]
    assert data["total_uses"] == 0


async def test_usage_summary_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{PROMOTIONS}/missing/usage-summary", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"
