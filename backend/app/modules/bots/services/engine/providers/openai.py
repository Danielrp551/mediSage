"""
Adaptador OpenAI (function calling). Contrato común `complete()`: recibe el system prompt, el
historial en formato NEUTRO (= OpenAI chat: role user/assistant/tool, assistant con `tool_calls`
anidados), las tools (subset común JSON Schema) y los params (temperature/max_tokens/top_p de
version.parameters). Devuelve ProviderResult. Credenciales: Settings.OPENAI_API_KEY (global por
entorno). Dep runtime: openai>=1.x (import LAZY dentro de complete → el boot/smoke sin la dep no
rompe).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings


@dataclass
class ProviderToolCall:
    tool_use_id: str  # id que devuelve el LLM para matchear el resultado
    name: str  # = BotTool.code
    arguments: dict[str, Any]


@dataclass
class ProviderResult:
    text: str | None  # respuesta en texto (si el modelo respondió al usuario)
    tool_calls: list[ProviderToolCall]  # vacío = no pidió tools → fin del loop
    tokens_in: int | None
    tokens_out: int | None
    raw: dict[str, Any] = field(default_factory=dict)  # fingerprint → BotEvent.metadata


_PARAM_KEYS = ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty")


def _tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


class OpenAIProvider:
    def __init__(self, model: str) -> None:
        self.model = model

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> ProviderResult:
        from openai import AsyncOpenAI  # import lazy (solo cuando se ejecuta un turno real)

        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        kwargs: dict[str, Any] = {"model": self.model, "messages": oai_messages}
        if tools:
            kwargs["tools"] = _tools_to_openai(tools)
            kwargs["tool_choice"] = "auto"
        for key in _PARAM_KEYS:
            if key in params and params[key] is not None:
                kwargs[key] = params[key]

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        tool_calls: list[ProviderToolCall] = []
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ProviderToolCall(tool_use_id=tc.id, name=tc.function.name, arguments=args)
            )
        usage = resp.usage
        return ProviderResult(
            text=choice.content,
            tool_calls=tool_calls,
            tokens_in=usage.prompt_tokens if usage else None,
            tokens_out=usage.completion_tokens if usage else None,
            raw={"model": resp.model, "finish_reason": resp.choices[0].finish_reason},
        )
