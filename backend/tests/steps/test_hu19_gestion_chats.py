"""
HU19 - Visualizar y gestionar chats de clientes/leads (control-plane).

Trazabilidad pytest-bdd (Anexo G.8): cada escenario Gherkin del backlog se ejecuta
como prueba automatizada. El marker `rf` vincula la prueba al Requerimiento Funcional.

Los chats nacen vía el webhook de WhatsApp (no hay endpoint público de creación): se firma
el body con el app_secret mockeado y se mockean los writers de Firestore + la resolución de
credenciales (sin GCP). `get_credentials` se monkeypatchea a nivel de módulo (el SyncBddClient
corre el mismo `app`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from pytest_bdd import given, scenarios, then, when

from app.core import firestore
from app.modules.conversations.services import channel_account as ca_service
from tests.steps.conftest import SyncBddClient

scenarios("hu19_gestion_chats.feature")

pytestmark = pytest.mark.rf("RF-E05-19")

AUTH = "/api/v1/admin/auth"
CONV = "/api/v1/conversations"
WEBHOOK = "/api/v1/webhooks/whatsapp"
APP_SECRET = "bdd-app-secret"


@pytest.fixture(autouse=True)
def _mock_externals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin GCP: mockea Firestore (relay) y la resolución de credenciales del canal."""
    monkeypatch.setattr(firestore, "write_message_doc", lambda *a, **k: None)
    monkeypatch.setattr(firestore, "upsert_conversation_doc", lambda *a, **k: None)
    monkeypatch.setattr(firestore, "update_message_status", lambda *a, **k: None)

    async def _fake_creds(db, ca):  # noqa: ANN001
        return {"access_token": "t", "app_secret": APP_SECRET, "phone_number_id": "PN"}

    monkeypatch.setattr(ca_service, "get_credentials", _fake_creds)


def _sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def _post_inbound(
    client: SyncBddClient, channel_id: str, wa_id: str, mid: str, text: str, ts: int
) -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": wa_id, "profile": {"name": f"Cliente {wa_id}"}}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": mid,
                                    "timestamp": str(ts),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    res = client.post(
        f"{WEBHOOK}/{channel_id}",
        content=raw,
        headers={"X-Hub-Signature-256": _sign(raw), "Content-Type": "application/json"},
    )
    assert res.status_code == 200, res.text


@pytest.fixture
def ctx() -> dict:
    return {}


@given("un asesor autenticado en el módulo de chats", target_fixture="auth_headers")
def _auth(bdd_client: SyncBddClient, bdd_admin: dict) -> dict[str, str]:
    res = bdd_client.post(f"{AUTH}/login", json=bdd_admin)
    assert res.status_code == 200, res.text
    body = res.json()
    return {"Authorization": f"Bearer {body['tokens']['access_token']}", "_uid": body["user"]["id"]}


@given("una cuenta de canal de WhatsApp registrada")
def _channel(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    res = bdd_client.post(
        f"{CONV}/channel-accounts",
        json={
            "channel_type": "whatsapp",
            "name": "WA BDD",
            "external_identifier": "bdd-channel-1",
        },
        headers={"Authorization": auth_headers["Authorization"]},
    )
    assert res.status_code == 201, res.text
    ctx["channel_id"] = res.json()["data"]["id"]


@given("un chat entrante de un contacto que es tomado por el asesor")
def _inbound_taken(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict) -> None:
    _post_inbound(bdd_client, ctx["channel_id"], "5210001112222", "wamid.BDD1", "Hola", int(time.time()))
    # Ubicar el chat recién creado y tomarlo (asignarlo al asesor).
    res = bdd_client.post(
        f"{CONV}/list?channel_account_id={ctx['channel_id']}",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers={"Authorization": auth_headers["Authorization"]},
    )
    assert res.status_code == 200, res.text
    cid = res.json()["data"]["items"][0]["id"]
    res = bdd_client.post(
        f"{CONV}/{cid}/take",
        json={},
        headers={"Authorization": auth_headers["Authorization"]},
    )
    assert res.status_code == 200, res.text
    ctx["conversation_id"] = cid


@given("un chat entrante de un contacto")
def _inbound(bdd_client: SyncBddClient, ctx: dict) -> None:
    _post_inbound(bdd_client, ctx["channel_id"], "5210003334444", "wamid.BDD2", "Consulta", int(time.time()))


@given("dos chats entrantes de contactos distintos en distinto momento")
def _two_inbound(bdd_client: SyncBddClient, ctx: dict) -> None:
    now = int(time.time())
    _post_inbound(bdd_client, ctx["channel_id"], "5210005550001", "wamid.OLD", "Antiguo", now - 7200)
    _post_inbound(bdd_client, ctx["channel_id"], "5210005550002", "wamid.NEW", "Reciente", now - 60)


@when("accede a la vista de chats en curso", target_fixture="response")
def _list(bdd_client: SyncBddClient, auth_headers: dict, ctx: dict):
    return bdd_client.post(
        f"{CONV}/list?channel_account_id={ctx['channel_id']}",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "sorting": {"sort_by": "last_message_at", "sort_order": "desc"},
        },
        headers={"Authorization": auth_headers["Authorization"]},
    )


@then("el sistema muestra la lista de chats indicando cliente/lead y asesor responsable")
def _verify_client_and_advisor(response, auth_headers: dict, ctx: dict) -> None:
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    item = next(i for i in items if i["id"] == ctx["conversation_id"])
    assert item["person"] is not None and item["person"]["full_name"]
    assert item["assignee_user"] is not None
    assert item["assignee_user"]["id"] == auth_headers["_uid"]


@then("los chats están ordenados por fecha y hora de la última interacción")
def _verify_order(response) -> None:
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    previews = [i["last_message_preview"] for i in items]
    assert previews.index("Reciente") < previews.index("Antiguo")


@then("se muestra el estado actual de cada chat")
def _verify_status(response) -> None:
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items, "se esperaba al menos un chat"
    assert all(i["status"] in ("open", "closed") for i in items)
