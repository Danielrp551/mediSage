"""
Helpers compartidos para los tests de integración de scheduling.

El dominio de citas tiene una cadena de dependencias profunda. Estos helpers
construyen TODO el escenario "bookeable" vía la API pública (en el orden de
dependencias de la guía): vertical → service → product, branch → office (apto
para el vertical) + operating-hours, doctor (con branch+vertical) + availability,
person. Devuelven un dict con todos los ids + un slot UTC válido listo para POST.

Convenciones del contrato (ver backend/CLAUDE.md y la guía de testing):
- create/get/update → envelope SingleResponse `{success, data}`.
- /list → `{success, data: {items, total, ...}}`.
- /active → lista cruda (sin envelope).
- POST /staff/doctors → DoctorCreatedResponse `{success, data, generated_password}`
  (data al tope, NO anidado en otro `data`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

ADMIN = "/api/v1/admin"
CATALOG = "/api/v1/catalog"
CLINIC = "/api/v1/clinic"
STAFF = "/api/v1/staff"
CRM = "/api/v1/crm"
SCHEDULING = "/api/v1/scheduling"


def _slug() -> str:
    """Slug minúsculo único válido para los `code` de catalog (a-z0-9_)."""
    return "t" + uuid.uuid4().hex[:10]


async def token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post(f"{ADMIN}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def auth_headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await token(client, admin_credentials)}"}


async def create_vertical(client: AsyncClient, headers: dict) -> str:
    r = await client.post(
        f"{CATALOG}/verticals",
        json={"code": _slug(), "name": "Vertical Test"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_service(client: AsyncClient, headers: dict, vertical_id: str) -> str:
    r = await client.post(
        f"{CATALOG}/services",
        json={"vertical_id": vertical_id, "code": _slug(), "name": "Servicio Test"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_product(
    client: AsyncClient,
    headers: dict,
    service_id: str,
    *,
    duration_min: int = 30,
    min_hours_to_cancel: int | None = None,
) -> str:
    body: dict = {
        "service_id": service_id,
        "code": _slug(),
        "name": "Producto Test",
        "base_price": "100.00",
        "duration_min": duration_min,
        "requires_appointment": True,
    }
    if min_hours_to_cancel is not None:
        body["min_hours_to_cancel"] = min_hours_to_cancel
    r = await client.post(f"{CATALOG}/products", json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_branch(client: AsyncClient, headers: dict) -> str:
    r = await client.post(
        f"{CLINIC}/branches",
        json={
            "code": _slug(),
            "name": "Sede Test",
            "address_line": "Av. Siempre Viva 123",
            "city": "Lima",
            # TZ con offset cero (Etc/UTC pasa el pattern Area/Location) para que los
            # tiempos locales == UTC en los tests → slot ISO == hora local del bloque.
            "timezone": "Etc/UTC",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def create_office(
    client: AsyncClient, headers: dict, branch_id: str, vertical_id: str
) -> str:
    r = await client.post(
        f"{CLINIC}/offices",
        json={
            "branch_id": branch_id,
            "code": _slug()[:20],
            "name": "Consultorio Test",
            "vertical_ids": [vertical_id],
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


async def set_office_hours(
    client: AsyncClient,
    headers: dict,
    office_id: str,
    *,
    opens: str = "00:00",
    closes: str = "23:59",
) -> None:
    """Abre el office todos los días de la semana (cobertura total para los slots)."""
    hours = [
        {"day_of_week": d, "opens_at": opens, "closes_at": closes} for d in range(7)
    ]
    r = await client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours",
        json={"hours": hours},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text


async def create_doctor(
    client: AsyncClient,
    headers: dict,
    *,
    branch_ids: list[str],
    vertical_ids: list[str],
    slot_duration_min: int = 30,
    active: bool = True,
) -> tuple[str, str]:
    """Crea User+Doctor anidado. Devuelve (doctor_id, user_id)."""
    r = await client.post(
        f"{STAFF}/doctors",
        json={
            "user": {
                "email": f"{_slug()}@example.com",
                "first_name": "Doc",
                "last_name": "Tor",
                "password": "ChangeMe123!",
            },
            "slot_duration_min": slot_duration_min,
            "branch_ids": branch_ids,
            "vertical_ids": vertical_ids,
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    detail = r.json()["data"]
    doctor_id, user_id = detail["id"], detail["user_id"]
    if not active:
        upd = await client.put(
            f"{STAFF}/doctors/{doctor_id}", json={"active": False}, headers=headers
        )
        assert upd.status_code == 200, upd.text
    return doctor_id, user_id


async def add_doctor_availability(
    client: AsyncClient,
    headers: dict,
    doctor_id: str,
    branch_id: str,
    office_id: str,
    *,
    date: str,
    opens_at: str = "08:00",
    closes_at: str = "18:00",
) -> None:
    r = await client.post(
        f"{STAFF}/doctors/{doctor_id}/availability",
        json={
            "blocks": [
                {
                    "branch_id": branch_id,
                    "office_id": office_id,
                    "date": date,
                    "opens_at": opens_at,
                    "closes_at": closes_at,
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text


async def token_for_limited_user(
    client: AsyncClient, admin_headers: dict, perm_codes: list[str]
) -> str:
    """Crea un usuario con EXACTAMENTE el conjunto de permisos `perm_codes` (vía
    permission_ids directos, sin rol) y devuelve su access token. Útil para
    ejercitar ramas que dependen de NO tener cierto permiso (p.ej. el override de
    cancelación). El usuario incluye siempre MENU-HOME para poder loguear/navegar."""
    active = await client.get(f"{ADMIN}/permissions/active", headers=admin_headers)
    assert active.status_code == 200, active.text
    by_code = {p["code"]: p["id"] for p in active.json()}
    wanted = set(perm_codes) | {"MENU-HOME"}
    perm_ids = [by_code[c] for c in wanted if c in by_code]
    email = f"{_slug()}@example.com"
    password = "ChangeMe123!"
    r = await client.post(
        f"{ADMIN}/users",
        json={
            "email": email,
            "first_name": "Limited",
            "last_name": "User",
            "permission_ids": perm_ids,
            "password": password,
        },
        headers=admin_headers,
    )
    assert r.status_code in (200, 201), r.text
    login = await client.post(f"{ADMIN}/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["tokens"]["access_token"]


async def create_person(client: AsyncClient, headers: dict, *, name: str = "Cliente") -> str:
    r = await client.post(
        f"{CRM}/persons",
        json={"first_name": name, "last_name": "Existente"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


class Scenario:
    """Bag de ids + un slot UTC válido para bookear. `next_monday` da una fecha
    futura determinista (lunes) para evitar el guard min_hours_to_cancel y para
    que el bloque de availability y la cita caigan en el mismo día local."""

    def __init__(self) -> None:
        self.vertical_id = ""
        self.service_id = ""
        self.product_id = ""
        self.branch_id = ""
        self.office_id = ""
        self.doctor_id = ""
        self.doctor_user_id = ""
        self.person_id = ""
        self.date = ""  # YYYY-MM-DD del bloque de disponibilidad
        self.scheduled_for = ""  # ISO UTC del inicio de la cita


def _booking_day(days_ahead: int = 14) -> datetime:
    """Día futuro a las 10:00 UTC. Por defecto a 2 semanas (>= cualquier
    min_hours_to_cancel ≤168h → no dispara el guard). Con days_ahead pequeño se
    fuerza una cita 'pronto' para ejercitar CANCEL_TOO_LATE."""
    return datetime.now(UTC).replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_ahead)


async def build_bookable_scenario(
    client: AsyncClient,
    headers: dict,
    *,
    duration_min: int = 30,
    slot_duration_min: int = 30,
    min_hours_to_cancel: int | None = None,
    doctor_active: bool = True,
    days_ahead: int = 14,
) -> Scenario:
    """Construye el escenario completo bookeable y devuelve el bag de ids + slot."""
    s = Scenario()
    s.vertical_id = await create_vertical(client, headers)
    s.service_id = await create_service(client, headers, s.vertical_id)
    s.product_id = await create_product(
        client,
        headers,
        s.service_id,
        duration_min=duration_min,
        min_hours_to_cancel=min_hours_to_cancel,
    )
    s.branch_id = await create_branch(client, headers)
    s.office_id = await create_office(client, headers, s.branch_id, s.vertical_id)
    await set_office_hours(client, headers, s.office_id)
    s.doctor_id, s.doctor_user_id = await create_doctor(
        client,
        headers,
        branch_ids=[s.branch_id],
        vertical_ids=[s.vertical_id],
        slot_duration_min=slot_duration_min,
        active=doctor_active,
    )
    monday = _booking_day(days_ahead)
    s.date = monday.date().isoformat()
    await add_doctor_availability(
        client, headers, s.doctor_id, s.branch_id, s.office_id, date=s.date
    )
    s.person_id = await create_person(client, headers)
    s.scheduled_for = monday.isoformat()
    return s


def appointment_payload(s: Scenario, **overrides) -> dict:
    body = {
        "person_id": s.person_id,
        "doctor_id": s.doctor_id,
        "office_id": s.office_id,
        "product_id": s.product_id,
        "scheduled_for": s.scheduled_for,
    }
    body.update(overrides)
    return body
