"""
Schemas Pydantic v2 del módulo `bots` (F1+). Variantes por entidad
(Create/Update/Item/Detail/Option) + requests específicos: `ActivateVersionRequest`,
`ResetBotStateRequest`, `DispatchTurnRequest {conversation_id, input_message_id?}`,
`ConfigurationToolsUpdate {tool_ids: list[str]}`. Espejan `frontend/src/types/bots.types.ts`.

El SECRETO del proveedor NUNCA viaja a un schema (las API keys son globales por entorno en
Settings; no hay campo de key por bot en el MVP). `BotConfigurationVersion.is_active` se expone
como flag (reusa `ActiveMixin.active`). INERTE en F0.
"""
