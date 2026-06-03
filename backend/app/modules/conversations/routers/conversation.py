"""
Conversation read endpoints (F2 — inbox de solo lectura). El aggregator ya pone el prefix
`/conversations`, así que este sub-router usa rutas raíz (`/list`, `/{id}`,
`/{id}/messages/list`). Permiso vía `dependencies=[Depends(RequirePermission(...))]`.

Deep-links del inbox como query params (NO en el body): `?channel_account_id=` / `?status=`
/ `?assignee_user_id=` / `?unassigned=true` → filtros sobre columnas reales en
`conversation_repository.list_inbox`. `defaultSort = last_message_at desc`. La búsqueda por
nombre/identificador es client-side (no son columnas de conversation).

F3 agrega las MUTACIONES: outbound (`POST /{id}/messages`) + handoff
(take/release/close/reopen/mark-read). Cada una llama al service (que muta el control plane
+ encola al outbox) y luego dispara el RELAY síncrono a Firestore (`message.relay_outbox`,
misma sesión) ANTES de responder — mismo patrón que el webhook (ver el análisis de
relay-síncrono en la memoria del módulo). `/me/conversations/list` vive en `routers/me.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.dependencies import CurrentAuth, DBSession, RequireAnyPermission, RequirePermission
from app.modules.conversations.schemas.conversation import (
    ConversationDetail,
    ConversationListItem,
    ReleaseConversationRequest,
    TakeConversationRequest,
)
from app.modules.conversations.schemas.message import MessageItem, MessageSendRequest
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
    # any-of: la bandeja global (CONVERSATIONS_READ) y "Mi bandeja" (MY_CONVERSATIONS_READ)
    # abren el hilo. El SERVICE scopea: un titular solo de MY_CONVERSATIONS_READ ve únicamente
    # los hilos asignados a él (los ajenos → 404). Sin esto, "Mi bandeja" no podría abrir el
    # detalle para un rol que NO tenga CONVERSATIONS_READ.
    dependencies=[Depends(RequireAnyPermission("CONVERSATIONS_READ", "MY_CONVERSATIONS_READ"))],
)
async def get_conversation(
    conversation_id: ConvIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ConversationDetail]:
    return await conversation_service.get_detail(
        db,
        conversation_id,
        actor_id=actor.id,
        can_read_all=actor.has_permission("CONVERSATIONS_READ"),
    )


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
    conversation_id: ConvIdPath, query: QueryRequest, db: DBSession, actor: CurrentAuth
) -> PaginatedResponse[MessageItem]:
    """FALLBACK server-side de lectura del hilo (lee Firestore vía Admin SDK). El path
    PRIMARIO es el cliente Firestore real-time (onSnapshot). El service scopea por actor:
    un titular solo de MY_CONVERSATIONS_READ lee únicamente los mensajes de sus hilos."""
    return await message_service.list_messages(
        db,
        conversation_id,
        query,
        actor_id=actor.id,
        can_read_all=actor.has_permission("CONVERSATIONS_READ"),
    )


# ── Mutaciones (F3) ──────────────────────────────────────────────────────────────
# Patrón: el service muta el control plane + encola al outbox; el HANDLER dispara el
# relay síncrono (`message_service.relay_outbox(db)`, misma sesión) ANTES de responder,
# para proyectar a Firestore (mensaje + conversation doc + allowed_reader_ids) sin
# BackgroundTasks (que no funciona confiable en Cloud Run — ver memoria del módulo).


@router.post(
    "/{conversation_id}/messages",
    response_model=SingleResponse[MessageItem],
    dependencies=[Depends(RequirePermission("MESSAGES_SEND"))],
)
async def send_message(
    conversation_id: ConvIdPath,
    payload: MessageSendRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[MessageItem]:
    """Envía un mensaje OUTBOUND (Meta real). 200 incluso si el envío falló (el mensaje se
    persiste `failed`; la UI reintenta). El service valida que el actor sea el asignado."""
    result = await message_service.send_outbound(db, conversation_id, payload, actor_id=actor.id)
    await message_service.relay_outbox(db)
    return result


@router.post(
    "/{conversation_id}/take",
    response_model=SingleResponse[ConversationDetail],
    dependencies=[Depends(RequirePermission("CONVERSATIONS_TAKE"))],
)
async def take_conversation(
    conversation_id: ConvIdPath,
    payload: TakeConversationRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ConversationDetail]:
    result = await conversation_service.take(
        db, conversation_id, actor_id=actor.id, reason=payload.reason
    )
    await message_service.relay_outbox(db)
    return result


@router.post(
    "/{conversation_id}/release",
    response_model=SingleResponse[ConversationDetail],
    dependencies=[Depends(RequirePermission("CONVERSATIONS_RELEASE"))],
)
async def release_conversation(
    conversation_id: ConvIdPath,
    payload: ReleaseConversationRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ConversationDetail]:
    result = await conversation_service.release(db, conversation_id, payload, actor_id=actor.id)
    await message_service.relay_outbox(db)
    return result


@router.post(
    "/{conversation_id}/close",
    response_model=SingleResponse[ConversationDetail],
    dependencies=[Depends(RequirePermission("CONVERSATIONS_CLOSE"))],
)
async def close_conversation(
    conversation_id: ConvIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ConversationDetail]:
    result = await conversation_service.close(db, conversation_id, actor_id=actor.id)
    await message_service.relay_outbox(db)
    return result


@router.post(
    "/{conversation_id}/reopen",
    response_model=SingleResponse[ConversationDetail],
    # Reabrir es la operación inversa de cerrar; el MVP la gatea con CONVERSATIONS_TAKE
    # (quien puede tomar un hilo puede reabrirlo). Valida no-otra-open (409).
    dependencies=[Depends(RequirePermission("CONVERSATIONS_TAKE"))],
)
async def reopen_conversation(
    conversation_id: ConvIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ConversationDetail]:
    result = await conversation_service.reopen(db, conversation_id, actor_id=actor.id)
    await message_service.relay_outbox(db)
    return result


@router.post(
    "/{conversation_id}/mark-read",
    response_model=SingleResponse[ConversationDetail],
    # any-of: todo titular del token de lectura (bandeja global o "mi bandeja") puede
    # marcar leída una conversación que ve (más robusto que el solo CONVERSATIONS_READ del
    # doc; alineado con el gate del token real-time y de /messages/list).
    dependencies=[Depends(RequireAnyPermission("CONVERSATIONS_READ", "MY_CONVERSATIONS_READ"))],
)
async def mark_conversation_read(
    conversation_id: ConvIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ConversationDetail]:
    result = await conversation_service.mark_read(
        db,
        conversation_id,
        actor_id=actor.id,
        can_read_all=actor.has_permission("CONVERSATIONS_READ"),
    )
    await message_service.relay_outbox(db)
    return result
