"""
HU24 - Registrar una nueva campaña.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se ejecuta como
prueba automatizada con el cliente SÍNCRONO `bdd_client`. El marker `rf` vincula la prueba
al Requerimiento Funcional de la épica de gestión de campañas.

Nota: la unicidad de campaña la impone la app por `code` (slug inmutable), no por nombre;
el escenario de unicidad se modela sobre el comportamiento real (código duplicado → 409).
"""

from __future__ import annotations

import uuid

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu24_registrar_campana.feature")

pytestmark = pytest.mark.rf("RF-E06-24")

AUTH = "/api/v1/admin/auth"
MARKETING = "/api/v1/marketing"


def _slug() -> str:
    return "c" + uuid.uuid4().hex[:10]


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un asesor autenticado en el módulo de campañas", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@when(
    parsers.parse(
        'registra una nueva campaña con nombre "{nombre}", descripción y fechas de inicio/fin'
    ),
    target_fixture="response",
)
def _register_full(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, nombre: str):
    body = {
        "code": _slug(),
        "name": nombre,
        "description": "Campaña de captación de pacientes",
        "start_date": "2026-01-01",
        "end_date": "2026-06-30",
    }
    ctx["nombre"] = nombre
    return bdd_client.post(f"{MARKETING}/campaigns", json=body, headers=auth_headers)


@then("el sistema debe permitir registrar la campaña con sus datos completos")
def _verify_full(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["name"] == ctx["nombre"]
    assert data["description"] == "Campaña de captación de pacientes"
    assert data["start_date"] == "2026-01-01"
    assert data["end_date"] == "2026-06-30"
    assert data["status"] == "draft"


@given(
    parsers.parse('ha registrado una nueva campaña con nombre "{nombre}"'),
    target_fixture="created_campaign",
)
def _registered(bdd_client: SyncBddClient, auth_headers: dict, nombre: str) -> dict:
    body = {"code": _slug(), "name": nombre, "start_date": "2026-01-01"}
    res = bdd_client.post(f"{MARKETING}/campaigns", json=body, headers=auth_headers)
    assert res.status_code == 201, res.text
    return res.json()["data"]


@when("consulta el historial de campañas", target_fixture="response")
def _list(bdd_client: SyncBddClient, auth_headers: dict):
    return bdd_client.post(
        f"{MARKETING}/campaigns/list",
        json={"pagination": {"skip": 0, "limit": 50}},
        headers=auth_headers,
    )


@then("la campaña registrada debe figurar en el historial de campañas")
def _verify_in_history(response, created_campaign: dict) -> None:
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert created_campaign["id"] in [c["id"] for c in items]


@given("ya existe una campaña con un código determinado", target_fixture="existing_campaign")
def _existing(bdd_client: SyncBddClient, auth_headers: dict) -> dict:
    code = _slug()
    body = {"code": code, "name": "Campaña Existente", "start_date": "2026-01-01"}
    res = bdd_client.post(f"{MARKETING}/campaigns", json=body, headers=auth_headers)
    assert res.status_code == 201, res.text
    return {"code": code, "id": res.json()["data"]["id"]}


@when("intenta registrar otra campaña con el mismo código", target_fixture="response")
def _register_dup(bdd_client: SyncBddClient, auth_headers: dict, existing_campaign: dict):
    body = {
        "code": existing_campaign["code"],
        "name": "Campaña Duplicada",
        "start_date": "2026-02-01",
    }
    return bdd_client.post(f"{MARKETING}/campaigns", json=body, headers=auth_headers)


@then("el sistema debe rechazar el registro por código duplicado")
def _verify_dup(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "CAMPAIGN_CODE_TAKEN"
