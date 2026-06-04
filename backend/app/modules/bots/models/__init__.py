"""
Importar los modelos aquí registra cada entidad en `Base.metadata` antes de que Alembic lea el
esquema y antes de resolver los `relationship(...)`/`ForeignKey(...)` por string.

⚠ Subset por fases (ver `docs/modules/bots/backend.md`):
- F1: `BotConfiguration`, `BotConfigurationVersion` (FK circular config↔version).
- F2: `BotTool` + M:N `bot_configuration_tool` (associations.py).
- F3: `ConversationBotState`, `BotEvent`, `BotToolCall` (trazas SIN SoftDelete;
  `BotEvent.input/output_message_id` = mid Firestore, varchar(255) NO FK).
"""

from app.modules.bots.models.bot_configuration import BotConfiguration
from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion

__all__ = [
    "BotConfiguration",
    "BotConfigurationVersion",
]
