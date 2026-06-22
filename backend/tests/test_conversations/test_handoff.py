"""
Tests de las acciones de HANDOFF (F3): take / release / close / reopen / mark-read.
Mutan el control plane + el ConversationAssignmentLog (audit) + encolan el espejo a
Firestore (mockeado). Happy paths + bordes (404, hilo cerrado, no-asignado, idempotencia,
guard de reapertura 409).
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


async def test_take_unassigned_conversation(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="take-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.unassigned,
        unread_count=5,
    )
    r = await client.post(f"{CONV}/{cid}/take", json={"reason": "Atiendo yo"}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["assignee_type"] == "advisor"
    assert data["assignee_user"]["id"] == uid
    assert data["unread_count"] == 0  # tomar = leer
    # El historial registró la transición.
    types = [log["to_assignee_type"] for log in data["assignment_history"]]
    assert "advisor" in types


async def test_take_closed_conversation_fails(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="take-closed-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        status=ConversationStatus.closed,
    )
    r = await client.post(f"{CONV}/{cid}/take", json={}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CONVERSATION_NOT_OPEN"


async def test_take_missing_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(f"{CONV}/nope/take", json={}, headers=headers)
    assert r.status_code == 404, r.text


async def test_release_to_unassigned(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="release-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/{cid}/release",
        json={"to_assignee_type": "unassigned", "reason": "Que lo tome otro"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["assignee_type"] == "unassigned"
    assert data["assignee_user"] is None


async def test_release_to_advisor_rejected(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="release-advisor-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/{cid}/release",
        json={"to_assignee_type": "advisor"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "INVALID_ASSIGNEE"


async def test_release_not_assignee_forbidden(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="release-notmine-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id="another-advisor",
    )
    r = await client.post(
        f"{CONV}/{cid}/release",
        json={"to_assignee_type": "unassigned"},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "NOT_CONVERSATION_ASSIGNEE"


async def test_release_to_bot_without_config_fails(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="release-bot-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(
        f"{CONV}/{cid}/release",
        json={"to_assignee_type": "bot"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "INVALID_ASSIGNEE"


async def test_close_and_reopen(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="close-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
    )
    r = await client.post(f"{CONV}/{cid}/close", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "closed"
    assert r.json()["data"]["closed_at"] is not None

    # Idempotente: cerrar de nuevo no falla.
    r = await client.post(f"{CONV}/{cid}/close", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "closed"

    # Reabrir.
    r = await client.post(f"{CONV}/{cid}/reopen", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "open"
    assert r.json()["data"]["closed_at"] is None


async def test_reopen_already_open_idempotent(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="reopen-open-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        status=ConversationStatus.open,
    )
    r = await client.post(f"{CONV}/{cid}/reopen", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "open"


async def test_reopen_conflicts_with_other_open(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    """Reabrir un hilo cerrado cuando ya existe OTRO abierto para el mismo (person, channel)
    → 409 CONVERSATION_ALREADY_OPEN (respeta el UNIQUE parcial 1-open)."""
    headers = await auth_headers(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="reopen-conflict-1")
    p = await create_person(client, headers)
    closed = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        status=ConversationStatus.closed,
    )
    # Otro hilo ABIERTO para el mismo par.
    await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        status=ConversationStatus.open,
    )
    r = await client.post(f"{CONV}/{closed}/reopen", headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CONVERSATION_ALREADY_OPEN"


async def test_mark_read_resets_unread(
    client: AsyncClient, admin_credentials: dict, session_factory: async_sessionmaker
) -> None:
    headers = await auth_headers(client, admin_credentials)
    uid = await admin_user_id(client, admin_credentials)
    ca = await create_channel_account(client, headers, external_identifier="markread-1")
    p = await create_person(client, headers)
    cid = await seed_conversation(
        session_factory,
        channel_account_id=ca["id"],
        person_id=p["id"],
        assignee_type=AssigneeType.advisor,
        assignee_user_id=uid,
        unread_count=7,
    )
    r = await client.post(f"{CONV}/{cid}/mark-read", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["unread_count"] == 0

    # Idempotente: ya en 0.
    r = await client.post(f"{CONV}/{cid}/mark-read", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["unread_count"] == 0


async def test_mark_read_missing_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(f"{CONV}/nope/mark-read", headers=headers)
    assert r.status_code == 404, r.text
