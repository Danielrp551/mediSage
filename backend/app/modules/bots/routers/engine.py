"""
Engine router. F3a expone SOLO `/engine/dispatch-manual` (RBAC BOT_ENGINE_INVOKE, debugging de
admin): corre el turno INLINE y dispara el relay síncrono del outbox a Firestore (mismo patrón que
el composer/webhook de conversations — evita el ciclo de import con conversation). El endpoint
interno `/engine/dispatch` (OIDC, target de Cloud Tasks) llega en F3b junto con `app/core/cloud_tasks.py`
— no se expone aún para no dejar un endpoint público sensible sin la cola cableada.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.bots.schemas.conversation_bot_state import ConversationBotStateDetail
from app.modules.bots.schemas.engine import DispatchTurnRequest
from app.modules.bots.services import conversation_bot_state as state_service
from app.modules.bots.services.engine import embedded as engine
from app.modules.conversations.services import message as conv_message
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/engine", tags=["bots · engine"])


@router.post(
    "/dispatch-manual",
    response_model=SingleResponse[ConversationBotStateDetail],
    dependencies=[Depends(RequirePermission("BOT_ENGINE_INVOKE"))],
)
async def dispatch_manual(
    payload: DispatchTurnRequest, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ConversationBotStateDetail]:
    """Dispatch MANUAL para debugging. Corre el turno inline y devuelve el estado resultante del
    bot. Útil en QA sin Cloud Tasks. El relay síncrono proyecta el outbound del bot a Firestore."""
    await engine.dispatch_turn(
        db, conversation_id=payload.conversation_id, input_message_id=payload.input_message_id
    )
    await conv_message.relay_outbox(db)
    return await state_service.get_state(db, payload.conversation_id)
