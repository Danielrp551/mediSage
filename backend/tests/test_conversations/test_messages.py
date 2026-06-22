"""
Tests del envío OUTBOUND (`send_outbound`) + el fallback de lectura del hilo
(`list_messages`). El envío real a Meta y la resolución de credenciales se mockean;
Firestore ya está mockeado por el conftest local. send_outbound SIEMPRE devuelve 200
(un fallo de envío persiste el mensaje `failed`, no 502).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.conversations.enums import AssigneeType, ConversationStatus
from app.modules.conversations.services import channel_account as ca_service
from app.modules.conversations.services.webhook_processor import whatsapp as wa
from tests.test_conversations.helpers import (
    CONV,
    admin_user_id,
    auth_headers,
    create_channel_account,
    create_person,
    seed_conversation,
)

pytestmark = pytest.mark.rf("RF-E05-19")


async def test_send_outbound_success(
    client: AsyncClient,
    admin_credentials: dict,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(
        client, headers, external_identifier="send-1", phone_number_id="PN1"
    )
    person = await create_person(client, headers, whatsapp_identifier="5215550001111")
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=person["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )

    async def _fake_creds(db, channel_account):  # noqa: ANN001
        return {"access_token": "tok", "app_secret": "sec", "phone_number_id": "PN1"}

    async def _fake_send_text(**kwargs):  # noqa: ANN003
        return "wamid.FAKE123"

    monkeypatch.setattr(ca_service, "get_credentials", _fake_creds)
    monkeypatch.setattr(wa, "send_text", _fake_send_text)

    r = await client.post(
        f"{CONV}/{cid}/messages",
        json={"content": "Hola, te ayudo"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    msg = r.json()["data"]
    assert msg["direction"] == "outbound"
    assert msg["sender_type"] == "advisor"
    assert msg["content"] == "Hola, te ayudo"
    assert msg["external_id"] == "wamid.FAKE123"
    assert msg["external_status"] == "sent"
    assert msg["sender_user"]["id"] == uid


async def test_send_outbound_persists_failed_when_no_identifier(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    """Sin identificador de WhatsApp el envío falla → mensaje `failed` pero 200 (no 502)."""
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="send-fail-1")
    person = await create_person(client, headers)  # sin identifier whatsapp
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=person["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/{cid}/messages",
        json={"content": "Intento"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    msg = r.json()["data"]
    assert msg["external_status"] == "failed"
    assert msg["failed_at"] is not None
    assert msg["failure_reason"]


async def test_send_outbound_closed_conversation_fails(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="send-closed-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
        status=ConversationStatus.closed,
    )
    r = await client.post(f"{CONV}/{cid}/messages", json={"content": "x"}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CONVERSATION_NOT_OPEN"


async def test_send_outbound_not_assignee_forbidden(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="send-notmine-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id="other-advisor",
    )
    r = await client.post(f"{CONV}/{cid}/messages", json={"content": "x"}, headers=headers)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "NOT_CONVERSATION_ASSIGNEE"


async def test_send_outbound_missing_conversation_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(f"{CONV}/nope/messages", json={"content": "x"}, headers=headers)
    assert r.status_code == 404, r.text


async def test_send_outbound_non_text_422(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    """El MVP solo admite texto → el validator del schema rechaza otros content_type."""
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="send-nontext-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/{cid}/messages",
        json={"content": "x", "content_type": "image"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_list_messages_fallback(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    """Fallback server-side de lectura del hilo (Firestore mockeado → lista vacía, total 0)."""
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="listmsg-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/{cid}/messages/list",
        json={"pagination": {"skip": 0, "limit": 20}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_messages_missing_conversation_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{CONV}/nope/messages/list",
        json={"pagination": {"skip": 0, "limit": 20}},
        headers=headers,
    )
    assert r.status_code == 404, r.text
