"""
Conversation read endpoints (F2 — inbox de solo lectura). El aggregator ya pone el prefix
`/conversations`, así que este sub-router usa rutas raíz (`/list`, `/{id}`,
`/{id}/messages/list`). Permiso vía `dependencies=[Depends(RequirePermission(...))]`.

Deep-links del inbox como query params (NO en el body): `?channel_account_id=` / `?status=`
/ `?assignee_user_id=` / `?unassigned=true` → filtros sobre columnas reales en
`conversation_repository.list_inbox`. `defaultSort = last_message_at desc`. La búsqueda por
nombre/identificador es client-side (no son columnas de conversation).

Las acciones de handoff (take/release/close/reopen/mark-read) + outbound (`POST /{id}/messages`)
+ `/me/conversations` llegan en F3.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.dependencies import DBSession, RequireAnyPermission, RequirePermission
from app.modules.conversations.schemas.conversation import (
    ConversationDetail,
    ConversationListItem,
)
from app.modules.conversations.schemas.message import MessageItem
from app.modules.conversations.services import conversation as conversation_service
from app.modules.conversations.services import message as message_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(tags=["conversations · inbox"])

ConvIdPath = Annotated[str, Path(min_length=1, description="Conversation UUID")]


@router.post(
    "/list",
    response_model=PaginatedResponse[ConversationListItem],
    dependencies=[Depends(RequirePermission("CONVERSATIONS_READ"))],
)
async def list_conversations(
    query: QueryRequest,
    db: DBSession,
    channel_account_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    assignee_user_id: Annotated[str | None, Query()] = None,
    unassigned: Annotated[bool | None, Query()] = None,
) -> PaginatedResponse[ConversationListItem]:
    return await conversation_service.list_inbox(
        db,
        query,
        channel_account_id=channel_account_id,
        status=status,
        assignee_user_id=assignee_user_id,
        unassigned=unassigned,
    )


@router.get(
    "/{conversation_id}",
    response_model=SingleResponse[ConversationDetail],
    dependencies=[Depends(RequirePermission("CONVERSATIONS_READ"))],
)
async def get_conversation(
    conversation_id: ConvIdPath, db: DBSession
) -> SingleResponse[ConversationDetail]:
    return await conversation_service.get_detail(db, conversation_id)


@router.post(
    "/{conversation_id}/messages/list",
    response_model=PaginatedResponse[MessageItem],
    # Mismo gate que el token real-time (realtime.py): el hilo se lee por Firestore
    # (CONVERSATIONS_READ|MY_CONVERSATIONS_READ) o por este FALLBACK server-side. Se alinean
    # los permisos para que el fallback sea accesible a todo titular del token (sino un rol
    # con solo MY_CONVERSATIONS_READ vería el hilo en vivo pero 403 al degradar). +MESSAGES_READ
    # por compat con quien ya lo tenía.
    dependencies=[
        Depends(
            RequireAnyPermission("CONVERSATIONS_READ", "MY_CONVERSATIONS_READ", "MESSAGES_READ")
        )
    ],
)
async def list_conversation_messages(
    conversation_id: ConvIdPath, query: QueryRequest, db: DBSession
) -> PaginatedResponse[MessageItem]:
    """FALLBACK server-side de lectura del hilo (lee Firestore vía Admin SDK). El path
    PRIMARIO es el cliente Firestore real-time (onSnapshot)."""
    return await message_service.list_messages(db, conversation_id, query)
