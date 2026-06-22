"""
HU28 - Configurar servicios que brinda una clínica.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se
ejecuta como prueba automatizada contra la API del módulo catalog. El servicio
de catálogo (`Service`) se asocia a una vertical (el contenedor del portafolio
de la clínica). El marker `rf` vincula la prueba al Requerimiento Funcional.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu28_configurar_servicios.feature")

pytestmark = pytest.mark.rf("RF-E08-28")

CATALOG = "/api/v1/catalog"
AUTH = "/api/v1/admin/auth"


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un administrador de clínica autenticado", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@given(parsers.parse('una vertical registrada con código "{code}"'))
def _vertical(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str) -> None:
    res = bdd_client.post(
        f"{CATALOG}/verticals",
        json={"code": code, "name": code.capitalize()},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    ctx["vertical_id"] = res.json()["data"]["id"]


@given(parsers.parse('un servicio "{code}" registrado en la vertical'))
def _existing_service(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str
) -> None:
    res = bdd_client.post(
        f"{CATALOG}/services",
        json={"vertical_id": ctx["vertical_id"], "code": code, "name": "Servicio"},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    ctx["service_id"] = res.json()["data"]["id"]


@when(
    parsers.parse('registra un servicio "{code}" con nombre "{name}"'),
    target_fixture="response",
)
def _register(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str, name: str):
    res = bdd_client.post(
        f"{CATALOG}/services",
        json={"vertical_id": ctx["vertical_id"], "code": code, "name": name},
        headers=auth_headers,
    )
    if res.status_code == 201:
        ctx["service_id"] = res.json()["data"]["id"]
    return res


@when(
    parsers.parse('registra un servicio "{code}" con descripción "{description}"'),
    target_fixture="response",
)
def _register_with_desc(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str, description: str
):
    res = bdd_client.post(
        f"{CATALOG}/services",
        json={
            "vertical_id": ctx["vertical_id"],
            "code": code,
            "name": code.capitalize(),
            "description": description,
        },
        headers=auth_headers,
    )
    if res.status_code == 201:
        ctx["service_id"] = res.json()["data"]["id"]
    ctx["expected_description"] = description
    return res


@when(parsers.parse('actualiza el nombre del servicio a "{name}"'), target_fixture="response")
def _update(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, name: str):
    return bdd_client.put(
        f"{CATALOG}/services/{ctx['service_id']}",
        json={"name": name},
        headers=auth_headers,
    )


@when("elimina el servicio", target_fixture="response")
def _delete(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.delete(
        f"{CATALOG}/services/{ctx['service_id']}", headers=auth_headers
    )


@when("consulta los servicios activos de la vertical", target_fixture="response")
def _list_active(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.get(
        f"{CATALOG}/services/active",
        params={"vertical_id": ctx["vertical_id"]},
        headers=auth_headers,
    )


@then("el sistema confirma el registro del servicio")
def _confirm_register(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    assert response.json()["data"]["id"] == ctx["service_id"]


@then("el sistema confirma la actualización del servicio")
def _confirm_update(response) -> None:
    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "Limpieza Premium"


@then("el sistema confirma la eliminación del servicio")
def _confirm_delete(response) -> None:
    assert response.status_code == 204, response.text


@then("el servicio queda asociado a la vertical y tiene la descripción registrada")
def _confirm_association(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["vertical_id"] == ctx["vertical_id"]
    assert data["description"] == ctx["expected_description"]


@then("el servicio aparece de inmediato en la lista de servicios activos")
def _confirm_reflected(response, ctx: dict) -> None:
    assert response.status_code == 200, response.text
    items = response.json()  # /active devuelve lista cruda
    assert ctx["service_id"] in [s["id"] for s in items]
