"""
Tests del INBOX de solo lectura (HU19): listar chats en curso (global + mi bandeja),
orden por última interacción, estado de cada chat, detalle con historial de handoff y
el token real-time. Las conversaciones se siembran directo en la BD (no hay endpoint
público de creación); Firestore está mockeado (conftest local).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.conversations.enums import AssigneeType, ConversationStatus
from tests.test_conversations.helpers import (
    CONV,
    admin_user_id,
    auth_headers,
    create_channel_account,
    create_person,
    seed_conversation,
)

pytestmark = pytest.mark.rf("RF-E05-19")


async def test_list_inbox_shows_conversations_with_person_and_channel(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="inbox-1")
    person = await create_person(client, headers, first_name="Maria", last_name="Lopez")
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=person["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
        unread_count=3,
    )

    r = await client.post(
        f"{CONV}/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    item = next(i for i in items if i["id"] == cid)
    # Escenario 1 (HU19): muestra cliente/lead y asesor responsable.
    assert item["person"]["full_name"].startswith("Maria")
    assert item["channel_account"]["id"] == ca["id"]
    assert item["assignee_user"]["id"] == uid
    # Escenario 3: estado actual del chat.
    assert item["status"] == "open"
    assert item["unread_count"] == 3


async def test_list_inbox_ordered_by_last_message_desc(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    """Escenario 2 (HU19): ordenados por fecha/hora de la última interacción (desc)."""
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="order-1")
    p1 = await create_person(client, headers, first_name="Antiguo")
    p2 = await create_person(client, headers, first_name="Reciente")
    old = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p1["id"],
        last_offset_minutes=120,
    )
    recent = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p2["id"],
        last_offset_minutes=1,
    )
    r = await client.post(
        f"{CONV}/list",
        json={
            "pagination": {"skip": 0, "limit": 10},
            "sorting": {"sort_by": "last_message_at", "sort_order": "desc"},
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["data"]["items"]]
    assert ids.index(recent) < ids.index(old)


async def test_list_inbox_filter_by_channel_and_status(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca1 = await create_channel_account(client, headers, external_identifier="ch-A")
    ca2 = await create_channel_account(client, headers, external_identifier="ch-B")
    p = await create_person(client, headers)
    in_a = await seed_conversation(
        session_factory, channel_account_id=ca1["id"], person_id=p["id"]
    )
    await seed_conversation(session_factory, channel_account_id=ca2["id"], person_id=None)

    r = await client.post(
        f"{CONV}/list?channel_account_id={ca1['id']}&status=open",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["data"]["items"]]
    assert in_a in ids
    assert all(i["channel_account"]["id"] == ca1["id"] for i in r.json()["data"]["items"])


async def test_list_inbox_filter_unassigned(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="unassigned-1")
    p1 = await create_person(client, headers)
    p2 = await create_person(client, headers)
    unassigned = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p1["id"],
        assignee_type=AssigneeType.unassigned,
    )
    assigned = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p2["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/list?unassigned=true",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["data"]["items"]]
    assert unassigned in ids
    assert assigned not in ids


async def test_get_detail_includes_assignment_history(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="detail-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.get(f"{CONV}/{cid}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == cid
    assert data["opened_at"]
    assert len(data["assignment_history"]) >= 1
    assert data["assignment_history"][0]["to_assignee_type"] == "advisor"


async def test_get_detail_missing_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.get(f"{CONV}/missing-conv", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CONVERSATION_NOT_FOUND"


async def test_my_inbox_returns_only_my_conversations(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="mine-1")
    p1 = await create_person(client, headers)
    p2 = await create_person(client, headers)
    mine = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p1["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    other = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p2["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id="some-other-user-id",
    )
    r = await client.post(
        f"{CONV}/me/conversations/list",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["data"]["items"]]
    assert mine in ids
    assert other not in ids


async def test_my_inbox_filter_by_status(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="mine-status-1")
    p1 = await create_person(client, headers)
    p2 = await create_person(client, headers)
    open_c = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p1["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
        status=ConversationStatus.open,
    )
    closed_c = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p2["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
        status=ConversationStatus.closed,
    )
    r = await client.post(
        f"{CONV}/me/conversations/list?status=open",
        json={"pagination": {"skip": 0, "limit": 10}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["data"]["items"]]
    assert open_c in ids
    assert closed_c not in ids


async def test_realtime_token_minted(
    client: AsyncClient, admin_credentials: dict, mock_firestore: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(f"{CONV}/realtime/token", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["token"].startswith("fake-custom-token-")
    # El admin tiene CONVERSATIONS_READ → claim can_read_all True.
    assert mock_firestore["mint_custom_token"]
    _uid, claims = mock_firestore["mint_custom_token"][0]
    assert claims["scope"] == "conversations"
    assert claims["can_read_all"] is True
