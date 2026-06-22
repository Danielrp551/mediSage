"""
HU04 - Realizar una "acción comercial" sobre un lead.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se ejecuta
como prueba automatizada. El marker `rf` vincula la prueba al Requerimiento
Funcional correspondiente. Cliente SÍNCRONO `bdd_client` (pytest-bdd no await-ea).
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu04_accion_comercial.feature")

pytestmark = pytest.mark.rf("RF-E01-04")

CRM = "/api/v1/crm"
AUTH = "/api/v1/admin/auth"


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un asesor autenticado en el módulo de leads", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@given("una persona registrada con un lead activo")
def _persona_con_lead(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.post(
        f"{CRM}/persons",
        json={"first_name": "Lead", "last_name": "Comercial"},
        headers=auth_headers,
    )
    assert res.status_code in (200, 201), res.text
    person_id = res.json()["data"]["id"]
    ctx["person_id"] = person_id
    lead = bdd_client.post(
        f"{CRM}/persons/{person_id}/lead-status", json={}, headers=auth_headers
    )
    assert lead.status_code == 201, lead.text


@when(
    parsers.parse(
        'registra una acción comercial de tipo "{tipo}" con la observación "{obs}"'
    ),
    target_fixture="response",
)
def _registra_accion(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, tipo: str, obs: str
):
    body = {"activity_type": tipo, "content": obs}
    if tipo == "CALL_ATTEMPT":
        body["outcome"] = "no_answer"
    res = bdd_client.post(
        f"{CRM}/persons/{ctx['person_id']}/activities",
        json=body,
        headers=auth_headers,
    )
    ctx["observation"] = obs
    if res.status_code in (200, 201):
        ctx["activity_id"] = res.json()["data"]["id"]
    return res


@then("el sistema responde con éxito y la acción queda registrada")
def _verify_registrada(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["id"] == ctx["activity_id"]
    assert data["content"] == ctx["observation"]


@then("la observación queda guardada y vinculada al lead")
def _verify_observacion(response, ctx: dict, bdd_client: SyncBddClient, auth_headers: dict) -> None:
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["content"] == ctx["observation"]
    assert data["person_id"] == ctx["person_id"]


@then("la acción aparece en el historial de actividades del lead")
def _verify_historial(
    response, ctx: dict, bdd_client: SyncBddClient, auth_headers: dict
) -> None:
    assert response.status_code == 201, response.text
    feed = bdd_client.post(
        f"{CRM}/persons/{ctx['person_id']}/activities/list",
        json={},
        headers=auth_headers,
    )
    assert feed.status_code == 200, feed.text
    ids = [a["id"] for a in feed.json()["data"]]
    assert ctx["activity_id"] in ids
