"""
Tests de integración del service de PromotionUsage (corazón de F3).

Cubre eligible-for / validate / compute-price / apply (redención) / list + el cálculo del
descuento (percentage cap, fixed_amount min) + elegibilidad (vigencia, cobertura, límites
total/por persona, no-stacking de cita) + 404 de FKs inexistentes.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_marketing._helpers import (
    MARKETING,
    auth_headers,
    create_full_product,
    create_person,
    create_promotion,
)

ELIGIBLE = f"{MARKETING}/promotions/eligible-for"
COMPUTE = f"{MARKETING}/compute-price"
USAGES = f"{MARKETING}/promotion-usages"


def _validate_url(promotion_id: str) -> str:
    return f"{MARKETING}/promotions/{promotion_id}/validate"


# ── compute-price ─────────────────────────────────────────────────────────────────────


async def test_compute_price_no_promo(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers, base_price="100.00")
    person_id = await create_person(client, headers)
    r = await client.post(
        COMPUTE,
        json={"product_id": product_id, "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["original_amount"] == "100.00"
    assert data["discount_amount"] == "0.00"
    assert data["final_amount"] == "100.00"
    assert data["promotion"] is None


async def test_compute_price_percentage(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers, base_price="100.00")
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client, headers, discount_type="percentage", discount_value="10.00"
    )
    r = await client.post(
        COMPUTE,
        json={"product_id": product_id, "person_id": person_id, "promotion_id": promo["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["discount_amount"] == "10.00"  # 10% de 100
    assert data["final_amount"] == "90.00"
    assert data["promotion"]["id"] == promo["id"]


async def test_compute_price_fixed_amount_capped(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """fixed_amount > base_price se capa al base_price (descuento nunca supera el precio)."""
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers, base_price="50.00")
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client, headers, discount_type="fixed_amount", discount_value="80.00"
    )
    r = await client.post(
        COMPUTE,
        json={"product_id": product_id, "person_id": person_id, "promotion_id": promo["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["discount_amount"] == "50.00"  # capado al base_price
    assert data["final_amount"] == "0.00"


async def test_compute_price_product_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person_id = await create_person(client, headers)
    r = await client.post(
        COMPUTE,
        json={"product_id": "missing", "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_compute_price_person_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    r = await client.post(
        COMPUTE,
        json={"product_id": product_id, "person_id": "missing"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


async def test_compute_price_promo_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    r = await client.post(
        COMPUTE,
        json={"product_id": product_id, "person_id": person_id, "promotion_id": "missing"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


# ── validate ──────────────────────────────────────────────────────────────────────────


async def test_validate_eligible(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers, base_price="100.00")
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client, headers, discount_value="10.00", applies_to_all_products=True
    )
    r = await client.post(
        _validate_url(promo["id"]),
        json={"product_id": product_id, "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["is_eligible"] is True
    assert data["reason"] is None
    assert data["discount_amount"] == "10.00"


async def test_validate_not_covered(client: AsyncClient, admin_credentials: dict) -> None:
    """Promo restringida a productos (applies_to_all_products=false) sin ese producto en su
    M:N → inelegible con reason PROMOTION_PRODUCT_NOT_COVERED."""
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=False)
    r = await client.post(
        _validate_url(promo["id"]),
        json={"product_id": product_id, "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["is_eligible"] is False
    assert data["reason"] == "PROMOTION_PRODUCT_NOT_COVERED"


async def test_validate_promo_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    r = await client.post(
        _validate_url("missing"),
        json={"product_id": product_id, "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


async def test_validate_product_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers)
    r = await client.post(
        _validate_url(promo["id"]),
        json={"product_id": "missing", "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


# ── eligible-for ──────────────────────────────────────────────────────────────────────


async def test_eligible_for_lists_covering_promos(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers, base_price="200.00")
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client, headers, discount_value="25.00", applies_to_all_products=True
    )
    r = await client.post(
        ELIGIBLE,
        json={"product_id": product_id, "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    ids = [e["promotion_id"] for e in data]
    assert promo["id"] in ids
    entry = next(e for e in data if e["promotion_id"] == promo["id"])
    assert entry["is_eligible"] is True
    assert entry["discount_amount"] == "50.00"  # 25% de 200


async def test_eligible_for_product_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person_id = await create_person(client, headers)
    r = await client.post(
        ELIGIBLE,
        json={"product_id": "missing", "person_id": person_id},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_eligible_for_person_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    r = await client.post(
        ELIGIBLE,
        json={"product_id": product_id, "person_id": "missing"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


# ── apply (redención) ─────────────────────────────────────────────────────────────────


async def test_apply_happy(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers, base_price="100.00")
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client, headers, discount_value="10.00", applies_to_all_products=True
    )
    r = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["promotion_id"] == promo["id"]
    assert data["original_amount"] == "100.00"
    assert data["discount_amount"] == "10.00"
    assert data["final_amount"] == "90.00"
    assert data["promotion_name"] == promo["name"]
    assert data["product_name"] == "Product Test"

    # usage-summary refleja el uso
    r = await client.get(
        f"{MARKETING}/promotions/{promo['id']}/usage-summary", headers=headers
    )
    assert r.status_code == 200, r.text
    summary = r.json()["data"]
    assert summary["total_uses"] == 1
    assert summary["total_discount_amount"] == "10.00"


async def test_apply_appears_in_list(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=True)
    apply = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert apply.status_code == 201, apply.text
    usage_id = apply.json()["data"]["id"]

    r = await client.post(
        f"{USAGES}/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert usage_id in [u["id"] for u in data["items"]]


async def test_apply_promo_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    r = await client.post(
        USAGES,
        json={"promotion_id": "missing", "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PROMOTION_NOT_FOUND"


async def test_apply_product_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=True)
    r = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": "missing"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_apply_person_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=True)
    r = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": "missing", "product_id": product_id},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PERSON_NOT_FOUND"


async def test_apply_appointment_404(client: AsyncClient, admin_credentials: dict) -> None:
    """Un appointment_id inexistente → 404 (no 500 por el FK)."""
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=True)
    r = await client.post(
        USAGES,
        json={
            "promotion_id": promo["id"],
            "person_id": person_id,
            "product_id": product_id,
            "appointment_id": "missing",
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "APPOINTMENT_NOT_FOUND"


async def test_apply_campaign_404(client: AsyncClient, admin_credentials: dict) -> None:
    """Un campaign_id inexistente → 404 (no 500 por el FK)."""
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=True)
    r = await client.post(
        USAGES,
        json={
            "promotion_id": promo["id"],
            "person_id": person_id,
            "product_id": product_id,
            "campaign_id": "missing",
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CAMPAIGN_NOT_FOUND"


async def test_apply_not_covered_400(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(client, headers, applies_to_all_products=False)
    r = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_PRODUCT_NOT_COVERED"


async def test_apply_total_limit_reached_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person1 = await create_person(client, headers, first_name="Ana")
    person2 = await create_person(client, headers, first_name="Beto")
    promo = await create_promotion(
        client, headers, applies_to_all_products=True, max_uses_total=1
    )
    first = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person1, "product_id": product_id},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person2, "product_id": product_id},
        headers=headers,
    )
    assert second.status_code == 400, second.text
    assert second.json()["code"] == "PROMOTION_LIMIT_REACHED"


async def test_apply_person_limit_reached_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client, headers, applies_to_all_products=True, max_uses_per_person=1
    )
    first = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert second.status_code == 400, second.text
    assert second.json()["code"] == "PROMOTION_PERSON_LIMIT_REACHED"


async def test_apply_expired_promo_400(client: AsyncClient, admin_credentials: dict) -> None:
    """Promo con vigencia ya vencida (end_date pasada) → PROMOTION_EXPIRED."""
    headers = await auth_headers(client, admin_credentials)
    product_id = await create_full_product(client, headers)
    person_id = await create_person(client, headers)
    promo = await create_promotion(
        client,
        headers,
        applies_to_all_products=True,
        start_date="2020-01-01",
        end_date="2020-12-31",
    )
    r = await client.post(
        USAGES,
        json={"promotion_id": promo["id"], "person_id": person_id, "product_id": product_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "PROMOTION_EXPIRED"
