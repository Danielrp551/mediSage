"""
Registry de tools del bot. Cada tool del catálogo (`bot_tool`) cuyo `code` esté registrado aquí
se puede invocar; si no → TOOL_NOT_REGISTERED (404) en runtime (F3). La key del registry = el
`code` de la BotTool (= el name que el LLM invoca; `@register_tool("list_verticals")`). El
`target_service` de la fila es referencia documental del catálogo; el dispatcher resuelve por
`code` (decisión backend.md §6-bis). El decorator `@register_tool` inscribe la función al importar
su módulo (`crm` / `catalog`) — por eso este `__init__` los importa AL FINAL (tras definir
`register_tool`), lo que dispara los decorators y deja `TOOL_REGISTRY` poblado al boot.

`BotInvocationContext` lleva el contexto sistémico (NO un CurrentAuth — las tools corren como
SYSTEM y validan reglas de negocio, ej. la matriz de transición de crm). En F2 las tools se
registran (para `is_registered`) pero el motor que las inyecta llega en F3.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BotInvocationContext:
    conversation_id: str
    person_id: str | None  # el contacto del hilo (puede ser None en bordes)
    bot_configuration_id: str
    bot_tool_call_id: str  # la traza BotToolCall en curso (para correlación)


# code -> async fn (args: dict, ctx, db) -> dict (el result que vuelve al LLM, JSON-serializable)
ToolFn = Callable[[dict[str, Any], BotInvocationContext, AsyncSession], Awaitable[dict[str, Any]]]
TOOL_REGISTRY: dict[str, ToolFn] = {}


def register_tool(code: str) -> Callable[[ToolFn], ToolFn]:
    def _wrap(fn: ToolFn) -> ToolFn:
        TOOL_REGISTRY[code] = fn
        return fn

    return _wrap


# Importar los módulos de tools DISPARA sus @register_tool (poblar TOOL_REGISTRY al boot).
# Va al final, tras definir register_tool/BotInvocationContext (los módulos importan de aquí).
from app.modules.bots.services.engine.tools import catalog as catalog  # noqa: E402,F401
from app.modules.bots.services.engine.tools import crm as crm  # noqa: E402,F401
from app.modules.bots.services.engine.tools import marketing as marketing  # noqa: E402,F401
from app.modules.bots.services.engine.tools import scheduling as scheduling  # noqa: E402,F401
