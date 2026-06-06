"""
Agrega los sub-routers de bots bajo un solo prefix. `main.py` incluye este `router` una sola vez.
El orden importa solo dentro de cada sub-router (/active antes de /{id}).

F1 expone `bot_configuration` (/configurations/* + /versions + activate-version). F2 agrega
`bot_tool` (/tools/*) y los endpoints M:N /configurations/{id}/tools. F3 agrega `engine`
(/engine/dispatch shared-secret [F3b] + /engine/dispatch-manual RBAC [F3a]) y `conversation_bot_state`
(/conversations/{cid}/state|events|tool-calls).
"""

from fastapi import APIRouter

from app.modules.bots.routers.bot_configuration import router as bot_configuration_router
from app.modules.bots.routers.bot_tool import router as bot_tool_router
from app.modules.bots.routers.conversation_bot_state import router as state_router
from app.modules.bots.routers.engine import router as engine_router

router = APIRouter(prefix="/bots")
router.include_router(
    bot_configuration_router
)  # /configurations/* (+ versions, activate, tools M:N)
router.include_router(bot_tool_router)  # /tools/*
router.include_router(
    engine_router
)  # /engine/dispatch-manual (RBAC) + /engine/dispatch (shared-secret)
router.include_router(state_router)  # /conversations/{cid}/state|events|tool-calls

__all__ = ["router"]
