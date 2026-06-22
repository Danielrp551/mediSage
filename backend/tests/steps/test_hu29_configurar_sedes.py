"""
HU29 - Configurar sedes que tiene una clínica.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se
ejecuta como prueba automatizada contra la API de sedes (branches) del módulo
clinic. El marker `rf` vincula la prueba al Requerimiento Funcional E08-HU29.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu29_configurar_sedes.feature")

pytestmark = pytest.mark.rf("RF-E08-29")

CLINIC = "/api/v1/clinic"
AUTH = "/api/v1/admin/auth"


@pytest.fixture
def ctx() -> dict:
    return {}


@given(
    "un administrador de clínica autenticado en el módulo Mi Clínica",
    target_fixture="auth_headers",
)
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@given(parsers.parse('una sede registrada con código "{code}"'))
def _sede_existente(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str
) -> None:
    res = bdd_client.post(
        f"{CLINIC}/branches",
        json={
            "code": code,
            "name": "Sede Existente",
            "address_line": "Calle 1",
            "city": "Lima",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    ctx["branch_id"] = res.json()["data"]["id"]


@when(parsers.parse('registra una sede con código "{code}"'))
def _registra_sede(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str
) -> None:
    res = bdd_client.post(
        f"{CLINIC}/branches",
        json={
            "code": code,
            "name": "Sede Central",
            "address_line": "Av. Central 100",
            "city": "Lima",
        },
        headers=auth_headers,
    )
    ctx["create_response"] = res
    if res.status_code == 201:
        ctx["branch_id"] = res.json()["data"]["id"]


@when("registra una sede con dirección, contacto y descripción")
def _registra_sede_completa(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict
) -> None:
    res = bdd_client.post(
        f"{CLINIC}/branches",
        json={
            "code": "sede_datos",
            "name": "Sede con Datos",
            "address_line": "Jr. Contacto 456",
            "district": "Miraflores",
            "city": "Lima",
            "phone": "+51 999 888 777",
            "email": "sede@clinica.test",
        },
        headers=auth_headers,
    )
    ctx["create_response"] = res


@when("consulta las sedes activas")
def _consulta_activas(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.get(f"{CLINIC}/branches/active", headers=auth_headers)
    ctx["active_response"] = res


@then("el sistema permite registrar la sede correctamente")
def _registro_ok(ctx: dict) -> None:
    res = ctx["create_response"]
    assert res.status_code == 201, res.text
    assert res.json()["data"]["code"] == "sede_central"


@then("al editar el nombre de la sede el cambio se guarda")
def _editar_ok(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.put(
        f"{CLINIC}/branches/{ctx['branch_id']}",
        json={"name": "Sede Central Editada"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["name"] == "Sede Central Editada"


@then("al eliminar la sede ya no se encuentra disponible")
def _eliminar_ok(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.delete(
        f"{CLINIC}/branches/{ctx['branch_id']}", headers=auth_headers
    )
    assert res.status_code == 204, res.text
    g = bdd_client.get(f"{CLINIC}/branches/{ctx['branch_id']}", headers=auth_headers)
    assert g.status_code == 404


@then("la sede registrada incluye dirección y datos de contacto")
def _datos_ok(ctx: dict) -> None:
    res = ctx["create_response"]
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["address_line"] == "Jr. Contacto 456"
    assert data["phone"] == "+51 999 888 777"
    assert data["email"] == "sede@clinica.test"


@then("la sede aparece en el listado de sedes activas")
def _aparece_en_activas(ctx: dict) -> None:
    res = ctx["active_response"]
    assert res.status_code == 200, res.text
    options = res.json()
    assert any(o["id"] == ctx["branch_id"] for o in options)
