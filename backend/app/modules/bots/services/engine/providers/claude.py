"""
Adaptador Claude (Anthropic tool use). Mismo contrato `complete()` y misma ProviderResult que el
adaptador OpenAI. Traduce el historial NEUTRO (formato OpenAI chat) a la forma de Claude: el system
va en `system`, los `tool_calls` del assistant → bloques `tool_use`, y los mensajes `role:tool` →
bloques `tool_result` agrupados en un mensaje `user` (Claude exige los tool_result juntos tras el
turno de tool_use). Credenciales: Settings.ANTHROPIC_API_KEY. Dep runtime: anthropic (ya está por
conversations); import LAZY dentro de complete.

⚠ F3a: este adaptador se IMPLEMENTA pero NO se valida end-to-end (no hay ANTHROPIC_API_KEY real en
el MVP; el secret arranca dummy). El adaptador OpenAI es el camino probado. Claude se validará
cuando se provisione una key real.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.modules.bots.services.engine.providers.openai import ProviderResult, ProviderToolCall


def _to_claude_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte el formato neutro (OpenAI chat) a la forma de Claude. Agrupa los `role:tool`
    consecutivos en un solo mensaje `user` con bloques tool_result."""
    out: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    def _flush_tool_results() -> None:
        if pending_tool_results:
            out.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for m in messages:
        role = m.get("role")
        if role == "tool":
            content = m.get("content")
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id"),
                    "content": content if isinstance(content, str) else json.dumps(content),
                }
            )
            continue
        _flush_tool_results()
        if role == "user":
            out.append({"role": "user", "content": m.get("content") or ""})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append(
                    {"type": "tool_use", "id": tc.get("id"), "name": fn.get("name"), "input": args}
                )
            out.append({"role": "assistant", "content": blocks or ""})
    _flush_tool_results()
    return out


def _tools_to_claude(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


class ClaudeProvider:
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
        from anthropic import AsyncAnthropic  # import lazy

        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": _to_claude_messages(messages),
            "max_tokens": params.get("max_tokens", 1024),
        }
        if tools:
            kwargs["tools"] = _tools_to_claude(tools)
        if params.get("temperature") is not None:
            kwargs["temperature"] = params["temperature"]
        if params.get("top_p") is not None:
            kwargs["top_p"] = params["top_p"]

        resp = await client.messages.create(**kwargs)
        text_parts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {}
                tool_calls.append(
                    ProviderToolCall(tool_use_id=block.id, name=block.name, arguments=args)
                )
        return ProviderResult(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            tokens_in=resp.usage.input_tokens if resp.usage else None,
            tokens_out=resp.usage.output_tokens if resp.usage else None,
            raw={"model": resp.model, "stop_reason": resp.stop_reason},
        )
