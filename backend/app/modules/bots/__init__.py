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

⚠ F0 (Prep): este paquete es un SKELETON INERTE — los `__init__.py` solo documentan la
estructura. **NO está registrado** en `app/modules/__init__.py` ni en `app/main.py` (lo cablea
F1, como hicieron crm/conversations). Sin modelos/migración todavía → no aporta tablas ni rutas.
"""
