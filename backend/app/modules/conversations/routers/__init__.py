"""
Agrega los sub-routers de conversations bajo un solo prefix. `main.py` incluye
este `router` una sola vez. El orden importa solo dentro de cada sub-router
(/active antes de /{id}); el orden del aggregator es informativo. El router de
webhooks es TOP-LEVEL (sin JWT) y vive en `app/routers/webhooks.py` — NO acá.

F1 expone `channel_account` (/channel-accounts/*). F2 agrega `conversation`
(/list, /{id}, take/release/close/reopen/mark-read, /messages/*), `realtime`
(/realtime/token, declarado ANTES de /{id} para no chocar con su captura) y `me`
(/me/conversations/list).
"""

from fastapi import APIRouter

from app.modules.conversations.routers.channel_account import (
    router as channel_account_router,
)

router = APIRouter(prefix="/conversations")
router.include_router(channel_account_router)  # /channel-accounts/*

__all__ = ["router"]
