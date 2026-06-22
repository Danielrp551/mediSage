"""
HU18 - Agregar citas sobre un cliente/lead existente.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se ejecuta
como prueba automatizada. El marker `rf` vincula la prueba al Requerimiento
Funcional correspondiente.

Los pasos usan el cliente SÍNCRONO `bdd_client` (pytest-bdd no await-ea async).
La cadena de prerequisitos (catalog → clinic → staff → crm) se construye inline con
llamadas síncronas, en el orden de dependencias del dominio de citas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pytest_bdd import given, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu18_registrar_cita.feature")

pytestmark = pytest.mark.rf("RF-E04-18")

ADMIN = "/api/v1/admin"
CATALOG = "/api/v1/catalog"
CLINIC = "/api/v1/clinic"
STAFF = "/api/v1/staff"
CRM = "/api/v1/crm"
SCHEDULING = "/api/v1/scheduling"


def _slug() -> str:
    return "h" + uuid.uuid4().hex[:10]


@pytest.fixture
def ctx() -> dict:
    return {}


@given(
    "un asesor autenticado con un escenario de agenda disponible",
    target_fixture="auth_headers",
)
def _scenario(bdd_client: SyncBddClient, ctx: dict) -> dict[str, str]:
    login = bdd_client.post(
        f"{ADMIN}/auth/login",
        json={"email": "admin@example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}

    vertical = bdd_client.post(
        f"{CATALOG}/verticals", json={"code": _slug(), "name": "Vert"}, headers=headers
    )
    assert vertical.status_code in (200, 201), vertical.text
    vertical_id = vertical.json()["data"]["id"]

    service = bdd_client.post(
        f"{CATALOG}/services",
        json={"vertical_id": vertical_id, "code": _slug(), "name": "Serv"},
        headers=headers,
    )
    assert service.status_code in (200, 201), service.text
    service_id = service.json()["data"]["id"]

    product = bdd_client.post(
        f"{CATALOG}/products",
        json={
            "service_id": service_id,
            "code": _slug(),
            "name": "Prod",
            "base_price": "100.00",
            "duration_min": 30,
            "requires_appointment": True,
        },
        headers=headers,
    )
    assert product.status_code in (200, 201), product.text
    ctx["product_id"] = product.json()["data"]["id"]

    branch = bdd_client.post(
        f"{CLINIC}/branches",
        json={
            "code": _slug(),
            "name": "Sede",
            "address_line": "Calle 1",
            "city": "Lima",
            "timezone": "Etc/UTC",
        },
        headers=headers,
    )
    assert branch.status_code in (200, 201), branch.text
    branch_id = branch.json()["data"]["id"]

    office = bdd_client.post(
        f"{CLINIC}/offices",
        json={
            "branch_id": branch_id,
            "code": _slug()[:20],
            "name": "Cons",
            "vertical_ids": [vertical_id],
        },
        headers=headers,
    )
    assert office.status_code in (200, 201), office.text
    office_id = office.json()["data"]["id"]
    ctx["office_id"] = office_id

    hours = bdd_client.put(
        f"{CLINIC}/offices/{office_id}/operating-hours",
        json={
            "hours": [
                {"day_of_week": d, "opens_at": "00:00", "closes_at": "23:59"}
                for d in range(7)
            ]
        },
        headers=headers,
    )
    assert hours.status_code in (200, 201), hours.text

    doctor = bdd_client.post(
        f"{STAFF}/doctors",
        json={
            "user": {
                "email": f"{_slug()}@example.com",
                "first_name": "Doc",
                "last_name": "Tor",
                "password": "ChangeMe123!",
            },
            "slot_duration_min": 30,
            "branch_ids": [branch_id],
            "vertical_ids": [vertical_id],
        },
        headers=headers,
    )
    assert doctor.status_code in (200, 201), doctor.text
    doctor_id = doctor.json()["data"]["id"]
    ctx["doctor_id"] = doctor_id

    when = datetime.now(UTC).replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(days=14)
    ctx["scheduled_for"] = when.isoformat()

    avail = bdd_client.post(
        f"{STAFF}/doctors/{doctor_id}/availability",
        json={
            "blocks": [
                {
                    "branch_id": branch_id,
                    "office_id": office_id,
                    "date": when.date().isoformat(),
                    "opens_at": "08:00",
                    "closes_at": "18:00",
                }
            ]
        },
        headers=headers,
    )
    assert avail.status_code in (200, 201), avail.text
    return headers


@given("un cliente registrado")
def _cliente(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.post(
        f"{CRM}/persons",
        json={"first_name": "Cliente", "last_name": "Existente"},
        headers=auth_headers,
    )
    assert res.status_code in (200, 201), res.text
    ctx["person_id"] = res.json()["data"]["id"]


@given("una cita ya registrada para el cliente en un horario")
def _cita_previa(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.post(
        f"{SCHEDULING}/appointments",
        json={
            "person_id": ctx["person_id"],
            "doctor_id": ctx["doctor_id"],
            "office_id": ctx["office_id"],
            "product_id": ctx["product_id"],
            "scheduled_for": ctx["scheduled_for"],
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text


@when("registra una nueva cita asociada al cliente existente", target_fixture="response")
def _registra(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.post(
        f"{SCHEDULING}/appointments",
        json={
            "person_id": ctx["person_id"],
            "doctor_id": ctx["doctor_id"],
            "office_id": ctx["office_id"],
            "product_id": ctx["product_id"],
            "scheduled_for": ctx["scheduled_for"],
        },
        headers=auth_headers,
    )


@when(
    "intenta registrar otra cita para el mismo cliente en el mismo horario",
    target_fixture="response",
)
def _registra_duplicada(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.post(
        f"{SCHEDULING}/appointments",
        json={
            "person_id": ctx["person_id"],
            "doctor_id": ctx["doctor_id"],
            "office_id": ctx["office_id"],
            "product_id": ctx["product_id"],
            "scheduled_for": ctx["scheduled_for"],
        },
        headers=auth_headers,
    )


@then("el sistema responde con éxito y la cita queda asociada al cliente")
def _verifica_creada(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["person_id"] == ctx["person_id"]
    ctx["appointment_id"] = data["id"]


@then("la cita queda registrada en el historial de citas del cliente")
def _verifica_historial(
    bdd_client: SyncBddClient, auth_headers: dict, response, ctx: dict
) -> None:
    assert response.status_code == 201, response.text
    appointment_id = response.json()["data"]["id"]
    listing = bdd_client.post(
        f"{SCHEDULING}/appointments/list",
        json={
            "pagination": {"skip": 0, "limit": 20},
            "filters": {
                "filters": [
                    {
                        "operator": "AND",
                        "conditions": [
                            {
                                "field": "person_id",
                                "operator": "eq",
                                "value": ctx["person_id"],
                            }
                        ],
                    }
                ]
            },
        },
        headers=auth_headers,
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()["data"]["items"]
    assert appointment_id in {i["id"] for i in items}
    assert all(i["person_id"] == ctx["person_id"] for i in items)


@then("el sistema rechaza la cita por duplicidad de horario")
def _verifica_duplicidad(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] in ("SLOT_TAKEN", "OFFICE_SLOT_TAKEN")
