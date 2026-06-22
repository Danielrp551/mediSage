"""
HU39 - Creación de un chatbot que maneje la atención al cliente y reservas de citas.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se ejecuta como prueba
automatizada. El marker `rf` vincula la prueba al Requerimiento Funcional correspondiente.

Adaptación de los escenarios del backlog a la API del módulo bots (single-tenant): "vincular a la
clínica" se materializa como "queda registrado y recuperable en el sistema"; "disponible de
inmediato" = aparece en el listado de bots activos; "responder a los usuarios" (que en runtime
requiere LLM + canal externo) se valida como "el bot queda operativo al tener una versión vigente".
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu39_crear_chatbot.feature")

pytestmark = pytest.mark.rf("RF-E10-39")

BOTS = "/api/v1/bots"
AUTH = "/api/v1/admin/auth"


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un administrador del sistema autenticado en el módulo de chatbots", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@given(parsers.parse('un chatbot creado con código "{code}"'))
def _bot_creado(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, code: str) -> None:
    res = bdd_client.post(
        f"{BOTS}/configurations",
        json={"code": code, "name": "Bot HU39", "bot_type": "general"},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    ctx["bot_id"] = res.json()["data"]["id"]
    ctx["bot_code"] = code


@when(
    parsers.parse(
        'crea un chatbot con nombre "{nombre}", tipo "{tipo}" y descripción "{descripcion}"'
    ),
    target_fixture="response",
)
def _crear_completo(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, nombre: str, tipo: str, descripcion: str
):
    res = bdd_client.post(
        f"{BOTS}/configurations",
        json={
            "code": "bot_recepcion",
            "name": nombre,
            "bot_type": tipo,
            "description": descripcion,
        },
        headers=auth_headers,
    )
    ctx["nombre"] = nombre
    ctx["tipo"] = tipo
    ctx["descripcion"] = descripcion
    return res


@when("el sistema confirma la creación", target_fixture="response")
def _confirma(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.get(f"{BOTS}/configurations/{ctx['bot_id']}", headers=auth_headers)


@when("el chatbot queda registrado en el sistema", target_fixture="response")
def _registrado(bdd_client: SyncBddClient, auth_headers: dict):
    return bdd_client.get(f"{BOTS}/configurations/active", headers=auth_headers)


@when("le crea una versión de comportamiento con un prompt", target_fixture="response")
def _crear_version(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.post(
        f"{BOTS}/configurations/{ctx['bot_id']}/versions",
        json={"system_prompt": "Eres el asistente de la clínica.", "provider": "openai"},
        headers=auth_headers,
    )


@then("el sistema permite crear el chatbot con los parámetros asignados")
def _verify_creado(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["name"] == ctx["nombre"]
    assert data["bot_type"] == ctx["tipo"]
    assert data["description"] == ctx["descripcion"]
    assert data["active"] is True


@then("el chatbot queda registrado y es recuperable en el sistema")
def _verify_registrado(response, ctx: dict) -> None:
    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == ctx["bot_id"]


@then("el chatbot está disponible de inmediato en el listado de bots activos")
def _verify_disponible(response, ctx: dict) -> None:
    assert response.status_code == 200, response.text
    body = response.json()  # /active devuelve lista cruda
    assert any(c["code"] == ctx["bot_code"] for c in body)


@then("el chatbot tiene una versión vigente y queda operativo")
def _verify_operativo(response, bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    version = response.json()["data"]
    assert version["is_current"] is True
    # el bot ahora tiene current_version_id (= operativo, usable por el motor)
    rc = bdd_client.get(f"{BOTS}/configurations/{ctx['bot_id']}", headers=auth_headers)
    assert rc.json()["data"]["current_version_id"] == version["id"]
