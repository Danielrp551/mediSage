"""
Services del módulo `bots` (F1+), módulos de funciones (no clases). Incluye el sub-paquete
`services/engine/` (ADR-005): `engine_factory(version)→BotEngine`, `BotEngine` (interfaz),
`EmbeddedBotEngine` (adaptadores `providers/{openai,claude}.py`), `tools/` (`TOOL_REGISTRY` +
`@register_tool` + `BotInvocationContext` + tools crm/catalog), y `dispatch_turn` (lo invoca
el endpoint `/engine/dispatch` que dispara Cloud Tasks, ADR-012). El relay/outbound del bot
reusa `conversations.message.send_bot_outbound` (cambio aditivo F3); el historial se lee de
Firestore (`conversations.firestore.list_message_docs`). INERTE en F0.
"""
