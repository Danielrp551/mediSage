"""
Tests del webhook de WhatsApp (entrypoint top-level, sin JWT). Cubre el flujo inbound
end-to-end del control plane: verify_signature (HMAC) → process_inbound → find_or_create_open
(crea Person + Conversation + primer assignment log) → persist_inbound (encola al outbox) →
relay_outbox (proyecta a Firestore, mockeado). También el challenge GET y los 403/404.

Las credenciales del canal (`get_credentials`, que da el app_secret) se mockean; la firma se
computa con ese mismo secreto. Firestore está mockeado por el conftest local.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from app.modules.conversations.services import channel_account as ca_service
from tests.test_conversations.helpers import (
    CONV,
    auth_headers,
    create_channel_account,
)

pytestmark = pytest.mark.rf("RF-E05-19")

WEBHOOK = "/api/v1/webhooks/whatsapp"
APP_SECRET = "test-app-secret"


def _sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def _inbound_payload(wa_id: str, mid: str, text: str = "Hola") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": wa_id, "profile": {"name": "Cliente WA"}}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": mid,
                                    "timestamp": "1700000000",
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


@pytest.fixture(autouse=True)
def _mock_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_creds(db, ca):  # noqa: ANN001
        return {
            "access_token": "tok",
            "app_secret": APP_SECRET,
            "phone_number_id": ca.phone_number_id or "PN",
        }

    monkeypatch.setattr(ca_service, "get_credentials", _fake_creds)


async def test_verify_challenge_ok(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(
        client, headers, external_identifier="wh-verify-1", webhook_verify_token="my-token"
    )
    r = await client.get(
        f"{WEBHOOK}/{ca['id']}",
        params={"hub.mode": "subscribe", "hub.verify_token": "my-token", "hub.challenge": "1234"},
    )
    assert r.status_code == 200, r.text
    assert r.text == "1234"


async def test_verify_challenge_bad_token_403(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(
        client, headers, external_identifier="wh-verify-2", webhook_verify_token="right"
    )
    r = await client.get(
        f"{WEBHOOK}/{ca['id']}",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert r.status_code == 403, r.text


async def test_verify_unknown_channel_404(client: AsyncClient) -> None:
    r = await client.get(
        f"{WEBHOOK}/nope",
        params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "x"},
    )
    assert r.status_code == 404, r.text


async def test_inbound_creates_conversation_and_relays(
    client: AsyncClient, admin_credentials: dict, mock_firestore: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="wh-in-1")
    payload = _inbound_payload("5219990001111", "wamid.AAA111")
    raw = json.dumps(payload).encode()

    r = await client.post(
        f"{WEBHOOK}/{ca['id']}",
        content=raw,
        headers={"X-Hub-Signature-256": _sign(raw), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True}
    # Relay proyectó el mensaje + el upsert del conversation a Firestore (mockeado).
    assert mock_firestore["write_message_doc"]
    assert mock_firestore["upsert_conversation_doc"]

    # La conversación quedó creada y aparece en el inbox con unread incrementado.
    r = await client.post(
        f"{CONV}/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    items = [i for i in r.json()["data"]["items"] if i["channel_account"]["id"] == ca["id"]]
    assert len(items) == 1
    assert items[0]["unread_count"] == 1
    assert items[0]["last_message_preview"] == "Hola"


async def test_inbound_idempotent_same_mid(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Reenvío del MISMO wamid no duplica ni vuelve a incrementar unread."""
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="wh-idem-1")
    payload = _inbound_payload("5219990002222", "wamid.DUP", text="Repetido")
    raw = json.dumps(payload).encode()
    sig = _sign(raw)

    r1 = await client.post(
        f"{WEBHOOK}/{ca['id']}",
        content=raw,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert r1.status_code == 200, r1.text
    r2 = await client.post(
        f"{WEBHOOK}/{ca['id']}",
        content=raw,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert r2.status_code == 200, r2.text

    r = await client.post(
        f"{CONV}/list?channel_account_id={ca['id']}",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["unread_count"] == 1  # NO se duplicó


async def test_inbound_bad_signature_403(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="wh-sig-1")
    payload = _inbound_payload("5219990003333", "wamid.SIG")
    raw = json.dumps(payload).encode()
    r = await client.post(
        f"{WEBHOOK}/{ca['id']}",
        content=raw,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "WEBHOOK_SIGNATURE_INVALID"


async def test_inbound_unknown_channel_404(client: AsyncClient) -> None:
    payload = _inbound_payload("521999", "wamid.X")
    raw = json.dumps(payload).encode()
    r = await client.post(
        f"{WEBHOOK}/missing-ca",
        content=raw,
        headers={"X-Hub-Signature-256": _sign(raw), "Content-Type": "application/json"},
    )
    assert r.status_code == 404, r.text


async def test_inbound_status_callback_best_effort(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Un batch con solo statuses[] (delivered) no rompe el 200 (best-effort)."""
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="wh-status-1")
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.STATUS",
                                    "status": "delivered",
                                    "timestamp": "1700000000",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    r = await client.post(
        f"{WEBHOOK}/{ca['id']}",
        content=raw,
        headers={"X-Hub-Signature-256": _sign(raw), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
