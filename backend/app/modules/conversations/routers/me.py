"""
Mi bandeja (F3). `POST /conversations/me/conversations/list` — las conversaciones cuyo
asesor asignado es el actor del token. Gateado por `MY_CONVERSATIONS_READ`. Es el análogo
de `/me/leads/list` de crm: el backend resuelve el actor del JWT (NO se acepta un
assignee_user_id arbitrario del cliente). Los deep-links de estado/canal van como query
params (igual que el inbox global); el filtro "sin asignar" no aplica en este scope.

El prefix del aggregator es `/conversations` y el de este sub-router `/me/conversations`,
de ahí la ruta final `/conversations/me/conversations/list` (espeja el endpoint declarado
en el front, `ENDPOINTS.ME_CONVERSATIONS.LIST`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.conversations.schemas.conversation import ConversationListItem
from app.modules.conversations.services import conversation as conversation_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest

router = APIRouter(prefix="/me/conversations", tags=["conversations · mi bandeja"])


@router.post(
    "/list",
    response_model=PaginatedResponse[ConversationListItem],
    dependencies=[Depends(RequirePermission("MY_CONVERSATIONS_READ"))],
)
async def list_my_conversations(
    query: QueryRequest,
    db: DBSession,
    actor: CurrentAuth,
    channel_account_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[ConversationListItem]:
    return await conversation_service.list_my_inbox(
        db,
        query,
        actor_id=actor.id,
        channel_account_id=channel_account_id,
        status=status,
    )
