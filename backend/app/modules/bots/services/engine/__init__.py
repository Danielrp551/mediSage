"""
Sub-paquete `engine` del módulo bots (ADR-005). Orquesta el turno del bot. Se construye por fases:

- F2: SOLO `engine.tools` (TOOL_REGISTRY + @register_tool + BotInvocationContext + las tools MVP
  crm/catalog). Es lo único que F2 necesita para el catálogo de tools (`is_registered`) — el
  motor en sí (que las invoca) llega en F3.
- F3a: `base.py` (interfaz BotEngine + choose_bot_for_conversation), `embedded.py`
  (EmbeddedBotEngine.dispatch_turn + loop de tool-calling + entrypoint `dispatch_turn`),
  `providers/{openai,claude}.py` (adaptadores con `complete()`), y el `engine_factory` (despacho por
  provider). `engine_factory` importa `embedded` de forma LAZY (dentro de la función) para que
  importar `engine.tools` (el registry, que necesita `bot_tool`) NO arrastre el motor + conversations.
- F3b: `app/core/cloud_tasks.py` (enqueue OIDC) + el path automático del webhook.
"""

from __future__ import annotations

from app.core.exceptions import BadRequestException
from app.modules.bots.enums import BotProvider
from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion
from app.modules.bots.services.engine.base import BotEngine

# Providers con adaptador en el MVP (Embedded). El resto (vertex_ai/azure_openai/external_webhook)
# está diseñado pero sin adaptador → PROVIDER_NOT_SUPPORTED en runtime.
_EMBEDDED_PROVIDERS = {BotProvider.openai, BotProvider.claude}


def engine_factory(version: BotConfigurationVersion) -> BotEngine:
    provider = BotProvider(version.provider)
    if provider in _EMBEDDED_PROVIDERS:
        # Import lazy: evita arrastrar embedded (conversations + repos) al importar engine.tools.
        from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

        return EmbeddedBotEngine()
    raise BadRequestException(
        f"El proveedor '{provider.value}' no está soportado en esta versión",
        code="PROVIDER_NOT_SUPPORTED",
    )
