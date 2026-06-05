"""
Sub-paquete `engine` del módulo bots (ADR-005). Orquesta el turno del bot. Se construye por fases:

- F2: SOLO `engine.tools` (TOOL_REGISTRY + @register_tool + BotInvocationContext + las tools MVP
  crm/catalog). Es lo único que F2 necesita para el catálogo de tools (`is_registered`) — el
  motor en sí (que las invoca) llega en F3.
- F3: `base.py` (interfaz BotEngine + choose_bot_for_conversation), `embedded.py`
  (EmbeddedBotEngine.dispatch_turn + loop de tool-calling), `providers/{openai,claude}.py`
  (adaptadores con `complete()`), y el `engine_factory` (despacho por provider). NO se declaran
  aquí en F2 para no arrastrar deps de LLM / conversations al import del catálogo de tools.
"""

from __future__ import annotations
