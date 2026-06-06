"""
Engine router. Dos entrypoints al motor del bot:
- `/engine/dispatch-manual` (RBAC BOT_ENGINE_INVOKE, F3a): debugging de admin; corre el turno INLINE.
- `/engine/dispatch` (shared-secret, F3b): target de Cloud Tasks (auto-path WhatsApp, ADR-012). SIN
  RBAC — lo autentica el header `X-Bot-Dispatch-Secret` (== `BOT_DISPATCH_SECRET`, comparado en tiempo
  constante con `hmac.compare_digest`, mismo primitivo que la firma de Meta). Ambos corren
  `engine.dispatch_turn` + el relay síncrono del outbox a Firestore (mismo patrón que el composer/
  webhook de conversations — evita el ciclo de import con conversation).
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.cloud_tasks import DISPATCH_SECRET_HEADER
from app.core.config import get_settings
from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.core.exceptions import ForbiddenException, NotFoundException
from app.modules.bots.schemas.conversation_bot_state import ConversationBotStateDetail
from app.modules.bots.schemas.engine import DispatchTurnRequest
from app.modules.bots.services import conversation_bot_state as state_service
from app.modules.bots.services.engine import embedded as engine
from app.modules.conversations.services import message as conv_message
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/engine", tags=["bots · engine"])


async def verify_dispatch_secret(
    x_bot_dispatch_secret: Annotated[str | None, Header(alias=DISPATCH_SECRET_HEADER)] = None,
) -> None:
    """Auth del endpoint interno `/engine/dispatch` (target de Cloud Tasks, sin RBAC): compara el
    header con `BOT_DISPATCH_SECRET` en TIEMPO CONSTANTE. Un secret CONFIGURADO vacío → 403 SIEMPRE
    (nunca aceptar un header ausente contra un secret vacío; el boot-validator ya impide arrancar con
    la cola habilitada y el secret vacío). Mismo primitivo que la firma de Meta (whatsapp.py)."""
    expected = get_settings().BOT_DISPATCH_SECRET.strip()
    provided = (x_bot_dispatch_secret or "").strip()
    if not expected or not hmac.compare_digest(provided, expected):
        raise ForbiddenException("Dispatch no autorizado", code="BOT_DISPATCH_UNAUTHORIZED")


@router.post(
    "/dispatch",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_dispatch_secret)],
)
async def dispatch(payload: DispatchTurnRequest, db: DBSession) -> dict[str, bool]:
    """Target de Cloud Tasks (auto-path WhatsApp). SIN RBAC: lo autentica el shared-secret. Corre el
    turno inline + el relay síncrono del outbound del bot a Firestore. Una conversación aún no visible
    (carrera commit del webhook → dispatch de la cola) → 503 para que Cloud Tasks reintente con
    backoff; un bot mal configurado o ya tomado por un asesor (NO_CURRENT_VERSION / CONVERSATION_NOT_BOT
    / CONVERSATION_NOT_OPEN) → 400 (4xx = no reintentar). Errores de provider/red ya se capturan dentro de
    `dispatch_turn` (turn_failed + fallback, sin 5xx)."""
    try:
        await engine.dispatch_turn(
            db, conversation_id=payload.conversation_id, input_message_id=payload.input_message_id
        )
    except NotFoundException as exc:
        # Carrera: el commit del webhook (get_db al cerrar el request) puede no haber materializado la
        # conversación cuando la task dispara. 503 → Cloud Tasks reintenta con backoff. La cola se
        # provisiona con reintentos GENEROSOS (max-attempts + max-backoff que cubran el p99 del cierre
        # del request) para absorber esta ventana. Solo se descarta tras agotar reintentos (borrado
        # genuino, o una indisponibilidad sostenida de la BD en la que igual todo falla); ese caso
        # extremo deja al contacto sin respuesta y sin traza turn_failed — handoff automático = F4.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversación aún no disponible; reintentar",
        ) from exc
    await conv_message.relay_outbox(db)
    return {"success": True}


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
