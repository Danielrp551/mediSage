"""
Agrega los sub-routers de bots bajo un solo prefix. `main.py` incluye este `router` una sola vez.
El orden importa solo dentro de cada sub-router (/active antes de /{id}).

F1 expone `bot_configuration` (/configurations/* + /versions + activate-version). F2 agrega
`bot_tool` (/tools/*) y los endpoints M:N /configurations/{id}/tools. F3 agrega `engine`
(/engine/dispatch OIDC + /engine/dispatch-manual RBAC) y `conversation_bot_state`
(/conversations/{cid}/state|events|tool-calls).
"""

from fastapi import APIRouter

from app.modules.bots.routers.bot_configuration import router as bot_configuration_router

router = APIRouter(prefix="/bots")
router.include_router(bot_configuration_router)  # /configurations/* (+ versions, activate-version)

__all__ = ["router"]
