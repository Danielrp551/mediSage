"""
bots enums. NINGUNO es catálogo en BD — son value sets a nivel de código (las columnas que
los referencian son varchar plano; Pydantic valida, la BD guarda el slug). `BotProvider` en el
MVP solo implementa openai (default) + claude; el resto (vertex_ai/azure_openai/external_webhook)
está DISEÑADO pero el adaptador NO existe → PROVIDER_NOT_SUPPORTED en runtime (F3). NO se
redefine `ChannelType` (el bot no la usa directo; las tools que tocan crm reusan crm.enums).
"""

from __future__ import annotations

from enum import StrEnum


class BotType(StrEnum):
    preventa = "preventa"
    postventa = "postventa"
    general = "general"
    custom = "custom"


class BotProvider(StrEnum):
    openai = "openai"  # MVP — default (gpt-4.1-mini)
    claude = "claude"  # MVP
    vertex_ai = "vertex_ai"  # diseñado, sin adaptador en el MVP
    azure_openai = "azure_openai"  # diseñado, sin adaptador en el MVP
    external_webhook = "external_webhook"  # ExternalBotEngine DIFERIDO


class ToolCallStatus(StrEnum):
    pending = "pending"
    success = "success"
    error = "error"
    timeout = "timeout"


class BotEventType(StrEnum):
    turn_started = "turn_started"
    turn_completed = "turn_completed"
    turn_failed = "turn_failed"
    tool_dispatched = "tool_dispatched"
    handoff_triggered = "handoff_triggered"  # handoff automático = F4 diferida
