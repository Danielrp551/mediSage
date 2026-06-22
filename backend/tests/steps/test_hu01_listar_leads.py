"""
HU01 - Visualizar los leads y aplicar filtros de búsqueda.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se
ejecuta como prueba automatizada. El marker `rf` vincula la prueba al
Requerimiento Funcional correspondiente.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

# Carga los escenarios del .feature (resuelto vía bdd_features_base_dir).
scenarios("hu01_listar_leads.feature")

pytestmark = pytest.mark.rf("RF-E01-01")

CRM = "/api/v1/crm"
AUTH = "/api/v1/admin/auth"


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un asesor autenticado", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@given(parsers.parse('una persona registrada con nombre "{nombre}"'))
def _persona(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, nombre: str) -> None:
    res = bdd_client.post(
        f"{CRM}/persons",
        json={"first_name": nombre, "last_name": "Apellido"},
        headers=auth_headers,
    )
    assert res.status_code in (200, 201), res.text
    ctx["person_id"] = res.json()["data"]["id"]


@when("solicita la lista de personas", target_fixture="response")
def _list(bdd_client: SyncBddClient, auth_headers: dict):
    return bdd_client.post(
        f"{CRM}/persons/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=auth_headers,
    )


@when(
    parsers.parse('solicita la lista de personas filtrando el nombre por "{nombre}"'),
    target_fixture="response",
)
def _list_filtered(bdd_client: SyncBddClient, auth_headers: dict, nombre: str):
    body = {
        "pagination": {"skip": 0, "limit": 10},
        "filters": {
            "filters": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "first_name", "operator": "contains", "value": nombre}
                    ],
                }
            ]
        },
    }
    return bdd_client.post(f"{CRM}/persons/list", json=body, headers=auth_headers)


@then("el sistema responde con éxito y la lista incluye la persona")
def _verify_includes(response, ctx: dict) -> None:
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert ctx["person_id"] in [item["id"] for item in data["items"]]


@then("el sistema responde con éxito y todos los resultados coinciden con el filtro")
def _verify_filter(response) -> None:
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items, "se esperaba al menos un resultado que coincida con el filtro"
    assert all("Ana" in item["first_name"] for item in items)
