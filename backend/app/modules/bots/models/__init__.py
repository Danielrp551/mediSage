"""
Importar los modelos aquí registra cada entidad en `Base.metadata` antes de que Alembic lea el
esquema y antes de resolver los `relationship(...)`/`ForeignKey(...)` por string.

⚠ Subset por fases (ver `docs/modules/bots/backend.md`):
- F1: `BotConfiguration`, `BotConfigurationVersion` (FK circular config↔version).
- F2: `BotTool` + M:N `bot_configuration_tool` (associations.py).
- F3: `ConversationBotState`, `BotEvent`, `BotToolCall` (trazas SIN SoftDelete;
  `BotEvent.input/output_message_id` = mid Firestore, varchar(255) NO FK).
"""

# Orden: associations + padres (bot_configuration, bot_tool) antes que el resto. El M:N referencia
# ambas tablas por string → se registra primero para que SQLAlchemy las resuelva. bot_event antes
# que bot_tool_call (que lo referencia por FK).
from app.modules.bots.models.associations import bot_configuration_tool
from app.modules.bots.models.bot_configuration import BotConfiguration
from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion
from app.modules.bots.models.bot_event import BotEvent
from app.modules.bots.models.bot_tool import BotTool
from app.modules.bots.models.bot_tool_call import BotToolCall
from app.modules.bots.models.conversation_bot_state import ConversationBotState

__all__ = [
    "bot_configuration_tool",
    "BotConfiguration",
    "BotConfigurationVersion",
    "BotTool",
    "ConversationBotState",
    "BotEvent",
    "BotToolCall",
]
