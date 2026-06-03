"""
Router del real-time token (ADR-011). `POST /conversations/realtime/token` mintea el
Firebase Custom Token para que el browser abra listeners READ-ONLY (signInWithCustomToken).
Gateado por `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` (RequireAnyPermission). Se
incluye ANTES del conversation_router en el aggregator (su `/realtime/token` no choca con
`/{id}`, pero el orden es defensivo). El RBAC del template es la fuente de verdad: gatea
quién recibe token y los claims (scope/can_read_all/is_advisor) que leen las Security Rules.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentAuth, RequireAnyPermission
from app.modules.conversations.schemas.realtime import RealtimeTokenResponse
from app.modules.conversations.services import realtime as realtime_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/realtime", tags=["conversations · realtime"])


@router.post(
    "/token",
    response_model=SingleResponse[RealtimeTokenResponse],
    dependencies=[Depends(RequireAnyPermission("CONVERSATIONS_READ", "MY_CONVERSATIONS_READ"))],
)
async def realtime_token(actor: CurrentAuth) -> SingleResponse[RealtimeTokenResponse]:
    return await realtime_service.mint_token(actor=actor)
