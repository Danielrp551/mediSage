"""
Adaptadores de proveedor del motor (ADR-005). Contrato común `complete(system, messages, tools,
params) -> ProviderResult`: el EmbeddedBotEngine habla con ProviderResult, no con OpenAI/Anthropic.
El formato NEUTRO de `messages` es el de OpenAI chat (role user/assistant/tool); el adaptador de
Claude lo traduce a su forma (tool_use/tool_result). Import LAZY de los SDK dentro de `complete`
(el boot/smoke sin las deps no rompe; el smoke mockea el adaptador).
"""

from __future__ import annotations
