"""
Módulo `bots` (#6) — motor conversacional configurable. Atiende automáticamente las
conversaciones de `conversations` cuando `Conversation.assignee_type='bot'`: cada inbound
dispara un TURNO del bot (LLM + tools), despachado **async vía Cloud Tasks** (ADR-012).

Agnóstico al motor (ADR-005): las entidades modelan qué bot existe, con qué prompt/versión,
qué tools puede usar y qué pasó en cada turno — sin atar la ejecución. MVP = `EmbeddedBotEngine`
multi-proveedor (OpenAI default `gpt-4.1-mini` + Claude); `ExternalBotEngine` diseñado pero
diferido. Mensajes en Firestore (ADR-011): `BotEvent.input/output_message_id` = el `mid`
(doc-id Firestore), NO FK.

Diseño completo: `docs/modules/bots/{README,backend,ui,frontend}.md` + ADR-005 (act.) + ADR-012.

Estado por fases: F1 cablea el paquete (registrado en `app/modules/__init__.py` + aggregator en
`app/main.py`) con `BotConfiguration` + `BotConfigurationVersion` (migr 0017). F2 agrega `BotTool`
+ M:N (0018). F3 agrega el engine + state + trazas + Cloud Tasks (0019).
"""
