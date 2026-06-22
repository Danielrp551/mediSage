"""
Helpers compartidos por los tests de integración de `conversations`.

El módulo NO expone un endpoint público para CREAR una conversación: el hilo nace
internamente vía `find_or_create_open` (webhook WhatsApp, con firma HMAC + relay a
Firestore). Para ejercitar el control-plane (lecturas del inbox + handoff
take/release/close/reopen/mark-read) sin montar todo el webhook, sembramos las
conversaciones DIRECTAMENTE en la BD de test (misma sesión sqlite que usa el `client`),
y mockeamos los writers de `app.core.firestore` para que el relay síncrono no toque GCP.

Los prerequisitos que SÍ tienen endpoint (channel_account, person) se crean vía API,
en orden de dependencias, igual que indica la guía.
"""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.conversations.enums import AssigneeType, ConversationStatus
from app.modules.conversations.models.conversation import Conversation
from app.modules.conversations.models.conversation_assignment_log import (
    ConversationAssignmentLog,
)
from app.shared.utils import generate_uuid, utc_now

ADMIN = "/api/v1/admin"
CRM = "/api/v1/crm"
CONV = "/api/v1/conversations"
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000002"


async def login(client: AsyncClient, admin_credentials: dict) -> dict:
    """Devuelve el cuerpo del login (tokens + user)."""
    r = await client.post(f"{ADMIN}/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()


async def token(client: AsyncClient, admin_credentials: dict) -> str:
    return (await login(client, admin_credentials))["tokens"]["access_token"]


async def auth_headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await token(client, admin_credentials)}"}


async def admin_user_id(client: AsyncClient, admin_credentials: dict) -> str:
    return (await login(client, admin_credentials))["user"]["id"]


async def create_channel_account(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str = "WA Principal",
    external_identifier: str | None = None,
    channel_type: str = "whatsapp",
    secret_name: str | None = None,
    webhook_verify_token: str | None = None,
    phone_number_id: str | None = None,
) -> dict:
    payload: dict = {
        "channel_type": channel_type,
        "name": name,
        "external_identifier": external_identifier or generate_uuid()[:18],
    }
    if secret_name is not None:
        payload["secret_name"] = secret_name
    if webhook_verify_token is not None:
        payload["webhook_verify_token"] = webhook_verify_token
    if phone_number_id is not None:
        payload["phone_number_id"] = phone_number_id
    r = await client.post(f"{CONV}/channel-accounts", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def create_person(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    first_name: str = "Juan",
    last_name: str = "Perez",
    whatsapp_identifier: str | None = None,
) -> dict:
    payload: dict = {"first_name": first_name, "last_name": last_name}
    if whatsapp_identifier is not None:
        payload["identifiers"] = [
            {"channel_type": "whatsapp", "identifier": whatsapp_identifier, "is_primary": True}
        ]
    r = await client.post(f"{CRM}/persons", json=payload, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


async def seed_conversation(
    session_factory: async_sessionmaker,
    *,
    channel_account_id: str,
    person_id: str | None,
    status: ConversationStatus = ConversationStatus.open,
    assignee_type: AssigneeType = AssigneeType.unassigned,
    assignee_user_id: str | None = None,
    unread_count: int = 0,
    last_offset_minutes: int = 0,
    with_log: bool = True,
) -> str:
    """Inserta una Conversation (y su primer ConversationAssignmentLog vigente) directo en la
    BD de test. Devuelve el conversation_id. `last_offset_minutes` desplaza `last_message_at`
    hacia atrás (para probar el orden por última interacción)."""
    now = utc_now()
    last_at = now - timedelta(minutes=last_offset_minutes)
    cid = generate_uuid()
    async with session_factory() as db:
        conv = Conversation(
            id=cid,
            channel_account_id=channel_account_id,
            person_id=person_id,
            status=status.value,
            assignee_type=assignee_type.value,
            assignee_user_id=assignee_user_id,
            bot_configuration_id=None,
            opened_at=now,
            closed_at=(now if status == ConversationStatus.closed else None),
            last_message_at=last_at,
            last_message_preview="Hola, necesito ayuda",
            unread_count=unread_count,
            active=True,
            created_by=SYSTEM_USER_ID,
            created_on=now,
            updated_by=SYSTEM_USER_ID,
            updated_on=now,
        )
        db.add(conv)
        if with_log:
            db.add(
                ConversationAssignmentLog(
                    id=generate_uuid(),
                    conversation_id=cid,
                    from_assignee_type=None,
                    from_assignee_user_id=None,
                    to_assignee_type=assignee_type.value,
                    to_assignee_user_id=assignee_user_id,
                    started_at=now,
                    ended_at=None,
                    by_actor_user_id=None,
                    reason="Auto-asignación",
                    active=True,
                    created_by=SYSTEM_USER_ID,
                    created_on=now,
                    updated_by=SYSTEM_USER_ID,
                    updated_on=now,
                )
            )
        await db.commit()
    return cid
