"""
Modelos SQLAlchemy del módulo `bots` (F1+). 7 entidades + M:N:
- `BotConfiguration` (F1) — bot lógico; apunta a su versión vigente.
- `BotConfigurationVersion` (F1) — prompt + provider + model + params (inmutable; rollback/A-B).
- `bot_configuration_tool` (F2, M:N en `models/associations.py`) — qué tools usa cada bot.
- `BotTool` (F2) — catálogo de funciones invocables (JSON Schema + target_service).
- `ConversationBotState` (F3) — estado del bot por conversación (UNIQUE conversation_id).
- `BotEvent` (F3) — traza por turno (SIN SoftDelete). `input/output_message_id`=mid Firestore, NO FK.
- `BotToolCall` (F3) — traza por invocación de tool (SIN SoftDelete).

Mixins: las 4 (PK·A·SD·T) salvo BotToolCall/BotEvent (PK·A·T, traza inmutable). Forward FKs
(ADR-009) de conversations (`channel_account.bot_configuration_id`, `conversation.bot_configuration_id`)
las cierra la migración de F1 (ALTER TABLE ADD CONSTRAINT, Postgres-only). INERTE en F0.
"""
