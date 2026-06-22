"""
HU32 - Asignar doctores a horarios.

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se
ejecuta como prueba automatizada. El marker `rf` vincula la prueba al
Requerimiento Funcional correspondiente.

En el módulo `staff`, "asignar un doctor a un horario" = crear un bloque de
disponibilidad del doctor en una sede/consultorio y franja horaria; "validar la
disponibilidad del doctor" = el invariante de no-solape (AVAILABILITY_OVERLAP).
"""

from __future__ import annotations

import itertools

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.steps.conftest import SyncBddClient

scenarios("hu32_asignar_doctores_horarios.feature")

pytestmark = pytest.mark.rf("RF-E08-32")

AUTH = "/api/v1/admin/auth"
CATALOG = "/api/v1/catalog"
CLINIC = "/api/v1/clinic"
STAFF = "/api/v1/staff"

_seq = itertools.count(1)


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un administrador de clínica autenticado", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}


@given("una sede con un consultorio registrados")
def _sede_consultorio(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    n = next(_seq)
    rb = bdd_client.post(
        f"{CLINIC}/branches",
        json={
            "code": f"hu32_branch_{n}",
            "name": f"Sede HU32 {n}",
            "address_line": "Av. Principal 100",
            "city": "Lima",
        },
        headers=auth_headers,
    )
    assert rb.status_code in (200, 201), rb.text
    ctx["branch_id"] = rb.json()["data"]["id"]
    ro = bdd_client.post(
        f"{CLINIC}/offices",
        json={"branch_id": ctx["branch_id"], "code": f"HU32-{n}", "name": f"Consultorio {n}"},
        headers=auth_headers,
    )
    assert ro.status_code in (200, 201), ro.text
    ctx["office_id"] = ro.json()["data"]["id"]


@given("un doctor asignado a esa sede")
def _doctor(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    n = next(_seq)
    res = bdd_client.post(
        f"{STAFF}/doctors",
        json={
            "user": {
                "email": f"hu32_doctor_{n}@example.com",
                "first_name": "Doc",
                "last_name": f"HU32_{n}",
            },
            "branch_ids": [ctx["branch_id"]],
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    ctx["doctor_id"] = res.json()["data"]["id"]


@given(
    parsers.parse(
        'el doctor ya tiene un horario "{opens}" a "{closes}" en esa sede y consultorio'
    )
)
def _existing_block(
    bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, opens: str, closes: str
) -> None:
    res = bdd_client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                {
                    "branch_id": ctx["branch_id"],
                    "office_id": ctx["office_id"],
                    "date": "2026-09-01",
                    "opens_at": opens,
                    "closes_at": closes,
                }
            ]
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text


@when(
    parsers.parse(
        'asigna al doctor un horario "{opens}" a "{closes}" en esa sede y consultorio'
    ),
    target_fixture="response",
)
def _assign(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict, opens: str, closes: str):
    return bdd_client.post(
        f"{STAFF}/doctors/{ctx['doctor_id']}/availability",
        json={
            "blocks": [
                {
                    "branch_id": ctx["branch_id"],
                    "office_id": ctx["office_id"],
                    "date": "2026-09-01",
                    "opens_at": opens,
                    "closes_at": closes,
                }
            ]
        },
        headers=auth_headers,
    )


@then("el sistema registra la asignación de disponibilidad del doctor")
def _ok(response, ctx: dict) -> None:
    assert response.status_code == 201, response.text
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["doctor_id"] == ctx["doctor_id"]


@then("el sistema rechaza la asignación por solapamiento de disponibilidad")
def _overlap(response) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "AVAILABILITY_OVERLAP"
