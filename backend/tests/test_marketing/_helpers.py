"""
Helpers compartidos por los tests de integración de `marketing`.

Crean los prerequisitos vía la API pública en orden de dependencias:
- catalog: vertical → service → product (para promotion M:N y compute/eligible/apply)
- crm: person (para eligible/validate/compute/apply)

El admin sembrado tiene TODOS los permisos → su token llama cualquier endpoint.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

AUTH = "/api/v1/admin/auth"
CATALOG = "/api/v1/catalog"
CRM = "/api/v1/crm"
MARKETING = "/api/v1/marketing"


def slug() -> str:
    """Slug minúsculo único válido contra CODE_PATTERN (^[a-z][a-z0-9_]{1,38}[a-z0-9]$)."""
    return "c" + uuid.uuid4().hex[:10]


async def token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post(f"{AUTH}/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def auth_headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await token(client, admin_credentials)}"}


async def create_vertical(client: AsyncClient, headers: dict) -> str:
    r = await client.post(
        f"{CATALOG}/verticals",
        json={"code": slug(), "name": "Vertical Test"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_service(client: AsyncClient, headers: dict, vertical_id: str) -> str:
    r = await client.post(
        f"{CATALOG}/services",
        json={"vertical_id": vertical_id, "code": slug(), "name": "Service Test"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_product(
    client: AsyncClient,
    headers: dict,
    service_id: str,
    *,
    base_price: str = "100.00",
    currency: str = "PEN",
) -> str:
    r = await client.post(
        f"{CATALOG}/products",
        json={
            "service_id": service_id,
            "code": slug(),
            "name": "Product Test",
            "base_price": base_price,
            "currency": currency,
            "requires_appointment": False,
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_full_product(
    client: AsyncClient, headers: dict, *, base_price: str = "100.00", currency: str = "PEN"
) -> str:
    """vertical → service → product en una sola llamada conveniente."""
    vertical_id = await create_vertical(client, headers)
    service_id = await create_service(client, headers, vertical_id)
    return await create_product(
        client, headers, service_id, base_price=base_price, currency=currency
    )


async def create_person(client: AsyncClient, headers: dict, *, first_name: str = "Juan") -> str:
    r = await client.post(
        f"{CRM}/persons",
        json={"first_name": first_name, "last_name": "Perez"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_campaign(
    client: AsyncClient,
    headers: dict,
    *,
    code: str | None = None,
    name: str = "Campaña Test",
    target_vertical_id: str | None = None,
    start_date: str = "2026-01-01",
    end_date: str | None = "2026-12-31",
) -> dict:
    body: dict = {"code": code or slug(), "name": name, "start_date": start_date}
    if end_date is not None:
        body["end_date"] = end_date
    if target_vertical_id is not None:
        body["target_vertical_id"] = target_vertical_id
    r = await client.post(f"{MARKETING}/campaigns", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def create_promotion(
    client: AsyncClient,
    headers: dict,
    *,
    code: str | None = None,
    name: str = "Promo Test",
    discount_type: str = "percentage",
    discount_value: str = "10.00",
    currency: str = "PEN",
    start_date: str = "2026-01-01",
    end_date: str | None = "2026-12-31",
    applies_to_all_products: bool = True,
    max_uses_total: int | None = None,
    max_uses_per_person: int | None = None,
) -> dict:
    body: dict = {
        "code": code or slug(),
        "name": name,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "currency": currency,
        "start_date": start_date,
        "applies_to_all_products": applies_to_all_products,
    }
    if end_date is not None:
        body["end_date"] = end_date
    if max_uses_total is not None:
        body["max_uses_total"] = max_uses_total
    if max_uses_per_person is not None:
        body["max_uses_per_person"] = max_uses_per_person
    r = await client.post(f"{MARKETING}/promotions", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]
