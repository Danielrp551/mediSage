"""
EmbeddedBotEngine: corre un turno completo del bot (flujo §1 de la spec). Lee el historial del hilo
de FIRESTORE (ADR-011), llama al adaptador del provider, corre el loop de tool-calling
(≤ MAX_TOOL_ITERATIONS_PER_TURN), responde con conversations.message.send_bot_outbound y persiste las
trazas (BotEvent / BotToolCall) + actualiza ConversationBotState. NO lanza 5xx salvo para forzar el
reintento de Cloud Tasks (los errores de provider se capturan → BotEvent(turn_failed) + fallback).

El dispatcher resuelve `TOOL_REGISTRY[tool.code]` (el registry se indexa por CODE; decisión §6-bis).
El formato NEUTRO de mensajes es OpenAI chat; el adaptador de Claude lo traduce.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import firestore
from app.core.config import get_settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.bots.enums import BotEventType, BotProvider, ToolCallStatus
from app.modules.bots.models.bot_event import BotEvent
from app.modules.bots.models.bot_tool import BotTool
from app.modules.bots.models.bot_tool_call import BotToolCall
from app.modules.bots.models.conversation_bot_state import ConversationBotState
from app.modules.bots.repositories.bot_configuration_version import (
    bot_configuration_version_repository,
)
from app.modules.bots.repositories.bot_event import bot_event_repository
from app.modules.bots.repositories.bot_tool import bot_tool_repository
from app.modules.bots.repositories.conversation_bot_state import (
    conversation_bot_state_repository,
)
from app.modules.bots.services.engine.base import BotEngine, choose_bot_for_conversation
from app.modules.bots.services.engine.providers.claude import ClaudeProvider
from app.modules.bots.services.engine.providers.openai import (
    OpenAIProvider,
    ProviderResult,
    ProviderToolCall,
)
from app.modules.bots.services.engine.tools import TOOL_REGISTRY, BotInvocationContext
from app.modules.conversations.enums import AssigneeType, ConversationStatus, MessageDirection
from app.modules.conversations.repositories.conversation import conversation_repository
from app.modules.conversations.services import message as conv_message
from app.modules.crm.services.person import SYSTEM_USER_ID
from app.shared.utils import generate_uuid, utc_now

logger = logging.getLogger(__name__)


class _ProviderAdapter(Protocol):
    """Contrato común de los adaptadores (OpenAIProvider/ClaudeProvider)."""

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> ProviderResult: ...


_PROVIDER_ADAPTERS: dict[BotProvider, Callable[[str], _ProviderAdapter]] = {
    BotProvider.openai: OpenAIProvider,
    BotProvider.claude: ClaudeProvider,
}

# Precio aproximado por 1M tokens (input, output) en USD — solo para el estimado de costo
# (BotEvent.cost_estimated_usd). Modelos desconocidos → None (sin estimado). Se ajusta a mano.
_MODEL_PRICES: dict[str, tuple[str, str]] = {
    "gpt-4.1-mini": ("0.40", "1.60"),
    "gpt-4.1": ("2.00", "8.00"),
    "gpt-4o-mini": ("0.15", "0.60"),
    "gpt-4o": ("2.50", "10.00"),
    "claude-sonnet-4-6": ("3.00", "15.00"),
    "claude-haiku-4-5": ("1.00", "5.00"),
    "claude-opus-4-8": ("5.00", "25.00"),
}

_DEFAULT_FALLBACK = "Disculpa, no pude procesar tu mensaje en este momento. Un asesor te atenderá."


def _map_history_to_messages(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Docs Firestore (cronológicos) → mensajes neutros (OpenAI chat). inbound(contacto)=user;
    outbound(bot/asesor)=assistant. Solo texto con contenido."""
    messages: list[dict[str, Any]] = []
    for d in docs:
        content = d.get("content")
        if not content or d.get("content_type") not in (None, "text"):
            continue
        role = "user" if d.get("direction") == MessageDirection.inbound.value else "assistant"
        messages.append({"role": role, "content": content})
    return messages


def _tool_to_schema(tool: BotTool) -> dict[str, Any]:
    return {
        "name": tool.code,
        "description": tool.description,
        "parameters": tool.parameters_schema or {"type": "object", "properties": {}},
    }


def _assistant_message(result: ProviderResult) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.text,
        "tool_calls": [
            {
                "id": tc.tool_use_id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in result.tool_calls
        ],
    }


def _tool_result_message(call: ProviderToolCall, tool_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.tool_use_id,
        "content": json.dumps(tool_result, default=str),
    }


def _estimate_cost(model_name: str, tokens_in: int, tokens_out: int) -> Decimal | None:
    prices = _MODEL_PRICES.get(model_name)
    if prices is None:
        return None
    in_price, out_price = Decimal(prices[0]), Decimal(prices[1])
    cost = (Decimal(tokens_in) * in_price + Decimal(tokens_out) * out_price) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _fallback_text(version: Any) -> str:
    params = version.parameters if isinstance(version.parameters, dict) else {}
    text = params.get("fallback_text")
    return text if isinstance(text, str) and text.strip() else _DEFAULT_FALLBACK


class EmbeddedBotEngine(BotEngine):
    async def dispatch_turn(
        self, db: AsyncSession, *, conversation_id: str, input_message_id: str | None
    ) -> None:
        settings = get_settings()
        # 0. cargar el hilo + validar que sea de bot.
        conv = await conversation_repository.get_by_id(db, conversation_id)
        if conv is None:
            raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
        if conv.assignee_type != AssigneeType.bot.value:
            raise BadRequestException(
                "La conversación no está asignada a un bot", code="CONVERSATION_NOT_BOT"
            )
        # Validar ABIERTO acá (no recién en send_bot_outbound) → no gasta una llamada al LLM en un
        # hilo cerrado (que pudo quedar assignee='bot' tras close, que no toca assignee_type).
        if conv.status != ConversationStatus.open.value:
            raise BadRequestException("La conversación está cerrada", code="CONVERSATION_NOT_OPEN")
        config = await choose_bot_for_conversation(db, conv)
        if config is None or config.current_version_id is None:
            raise BadRequestException("El bot no tiene versión vigente", code="NO_CURRENT_VERSION")
        version = await bot_configuration_version_repository.get_by_id(
            db, config.current_version_id
        )
        if version is None:
            raise BadRequestException("El bot no tiene versión vigente", code="NO_CURRENT_VERSION")

        # 1. ConversationBotState (load-or-create) — congela la versión con la que arranca el hilo.
        state = await conversation_bot_state_repository.get_by_conversation(db, conversation_id)
        if state is None:
            now0 = utc_now()
            state = ConversationBotState(
                id=generate_uuid(),
                conversation_id=conversation_id,
                bot_configuration_id=config.id,
                bot_configuration_version_id=version.id,
                collected_slots={},
                turn_count=0,
                active=True,
                created_by=SYSTEM_USER_ID,
                created_on=now0,
                updated_by=SYSTEM_USER_ID,
                updated_on=now0,
            )
            db.add(state)
            await db.flush()

        # Guard de costo: max_turns_per_conversation (None = sin límite).
        if (
            config.max_turns_per_conversation is not None
            and state.turn_count >= config.max_turns_per_conversation
        ):
            logger.info("bot turn cap reached", extra={"conversation_id": conversation_id})
            return  # silencioso (el handoff automático a humano = F4)

        # 2. BotEvent(turn_started).
        turn_number = await bot_event_repository.max_turn_number(db, conversation_id) + 1
        started = utc_now()
        event = BotEvent(
            id=generate_uuid(),
            conversation_id=conversation_id,
            bot_configuration_id=config.id,
            bot_configuration_version_id=version.id,
            turn_number=turn_number,
            event_type=BotEventType.turn_started.value,
            input_message_id=input_message_id,
            active=True,
            created_by=SYSTEM_USER_ID,
            created_on=started,
            updated_by=SYSTEM_USER_ID,
            updated_on=started,
        )
        db.add(event)
        await db.flush()

        # 3. prompt = system_prompt + historial Firestore + tools (M:N ∩ active).
        history, _ = await asyncio.to_thread(
            firestore.list_message_docs, conversation_id, skip=0, limit=50
        )
        messages = _map_history_to_messages(history)
        tools_models = await bot_tool_repository.active_tools_for_config(db, config.id)
        tools_defs = [_tool_to_schema(t) for t in tools_models]
        tool_by_code = {t.code: t for t in tools_models}

        # 4. adaptador del provider (engine_factory ya eligió EmbeddedBotEngine).
        adapter = _PROVIDER_ADAPTERS[BotProvider(version.provider)](version.model_name)
        params = version.parameters if isinstance(version.parameters, dict) else {}

        # 5. loop de tool-calling (≤ MAX_TOOL_ITERATIONS_PER_TURN).
        tokens_in = tokens_out = 0
        output_text: str | None = None
        for _ in range(settings.MAX_TOOL_ITERATIONS_PER_TURN):
            result = await adapter.complete(
                system=version.system_prompt,
                messages=messages,
                tools=tools_defs,
                params=params,
            )
            tokens_in += result.tokens_in or 0
            tokens_out += result.tokens_out or 0
            if not result.tool_calls:
                output_text = result.text
                break
            messages.append(_assistant_message(result))
            for call in result.tool_calls:
                tool_model = tool_by_code.get(call.name)
                if tool_model is None:
                    # El modelo pidió una tool que el bot NO tiene asignada → reportar, sin traza
                    # (no hay bot_tool_id para persistir la BotToolCall).
                    messages.append(
                        _tool_result_message(call, {"ok": False, "error": "tool_not_available"})
                    )
                    continue
                tc = BotToolCall(
                    id=generate_uuid(),
                    conversation_id=conversation_id,
                    bot_event_id=event.id,
                    bot_tool_id=tool_model.id,
                    tool_use_id=call.tool_use_id,
                    arguments=call.arguments,
                    status=ToolCallStatus.pending.value,
                    started_at=utc_now(),
                    active=True,
                    created_by=SYSTEM_USER_ID,
                    created_on=utc_now(),
                    updated_by=SYSTEM_USER_ID,
                    updated_on=utc_now(),
                )
                db.add(tc)
                await db.flush()
                fn = TOOL_REGISTRY.get(tool_model.code)  # resuelve por CODE (§6-bis)
                if fn is None:
                    tc.status = ToolCallStatus.error.value
                    tc.error_message = "TOOL_NOT_REGISTERED"
                    tool_result: dict[str, Any] = {"ok": False, "error": "tool_not_registered"}
                else:
                    ctx = BotInvocationContext(
                        conversation_id=conversation_id,
                        person_id=conv.person_id,
                        bot_configuration_id=config.id,
                        bot_tool_call_id=tc.id,
                    )
                    t0 = utc_now()
                    try:
                        # Savepoint: un error de BD dentro de la tool (flush/constraint) revierte
                        # SOLO su trabajo, sin envenenar la sesión del turno (tc ya está flusheado
                        # antes del savepoint; la traza + el resto del loop siguen vivos).
                        async with db.begin_nested():
                            tool_result = await fn(call.arguments, ctx, db)
                        tc.status = ToolCallStatus.success.value
                    except Exception as exc:  # noqa: BLE001 — reportar al LLM, no romper el turno
                        tc.status = ToolCallStatus.error.value
                        tc.error_message = str(exc)[:1000]
                        tool_result = {"ok": False, "error": str(exc)[:255]}
                    tc.latency_ms = int((utc_now() - t0).total_seconds() * 1000)
                tc.result = tool_result
                tc.completed_at = utc_now()
                messages.append(_tool_result_message(call, tool_result))
            await db.flush()
        else:
            # agotó las iteraciones sin una respuesta final → fallback configurable.
            output_text = _fallback_text(version)

        # 6. responder por WhatsApp reusando conversations (sender_type='bot').
        output_mid: str | None = None
        if output_text:
            sent = await conv_message.send_bot_outbound(
                db, conv, output_text, bot_configuration_id=config.id
            )
            output_mid = sent.data.id

        # 7. update ConversationBotState + BotEvent(turn_completed).
        ended = utc_now()
        state.turn_count += 1
        state.last_bot_turn_at = ended
        state.updated_by = SYSTEM_USER_ID
        state.updated_on = ended
        db.add(
            BotEvent(
                id=generate_uuid(),
                conversation_id=conversation_id,
                bot_configuration_id=config.id,
                bot_configuration_version_id=version.id,
                turn_number=turn_number,
                event_type=BotEventType.turn_completed.value,
                input_message_id=input_message_id,
                output_message_id=output_mid,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=int((ended - started).total_seconds() * 1000),
                cost_estimated_usd=_estimate_cost(version.model_name, tokens_in, tokens_out),
                event_metadata={"provider": version.provider, "model": version.model_name},
                active=True,
                created_by=SYSTEM_USER_ID,
                created_on=ended,
                updated_by=SYSTEM_USER_ID,
                updated_on=ended,
            )
        )
        await db.flush()


async def _log_turn_failed(db: AsyncSession, conversation_id: str, *, error: str) -> None:
    """Escribe un BotEvent(turn_failed) + intenta enviar un fallback (best-effort). No re-lanza."""
    try:
        # La sesión pudo quedar ENVENENADA por el error que disparó este path (un flush fallido
        # deja la AsyncSession en "needs rollback"). Rollback para escribir la traza inmutable + el
        # fallback sobre una sesión limpia (se descarta el turn_started/parcial de este turno — la
        # red de seguridad pesa más que la traza parcial).
        await db.rollback()
        conv = await conversation_repository.get_by_id(db, conversation_id)
        if conv is None or conv.bot_configuration_id is None:
            return
        config = await choose_bot_for_conversation(db, conv)
        version = (
            await bot_configuration_version_repository.get_by_id(db, config.current_version_id)
            if config is not None and config.current_version_id is not None
            else None
        )
        if config is None or version is None:
            return
        turn_number = await bot_event_repository.max_turn_number(db, conversation_id) + 1
        now = utc_now()
        db.add(
            BotEvent(
                id=generate_uuid(),
                conversation_id=conversation_id,
                bot_configuration_id=config.id,
                bot_configuration_version_id=version.id,
                turn_number=turn_number,
                event_type=BotEventType.turn_failed.value,
                error=error[:2000],
                active=True,
                created_by=SYSTEM_USER_ID,
                created_on=now,
                updated_by=SYSTEM_USER_ID,
                updated_on=now,
            )
        )
        await db.flush()
        if conv.assignee_type == AssigneeType.bot.value:
            await conv_message.send_bot_outbound(
                db, conv, _fallback_text(version), bot_configuration_id=config.id
            )
    except Exception as exc:  # noqa: BLE001 — el log de la falla NO debe romper el request
        logger.warning(
            "could not log turn_failed",
            extra={"conversation_id": conversation_id, "error": str(exc)},
        )


async def dispatch_turn(
    db: AsyncSession, *, conversation_id: str, input_message_id: str | None
) -> None:
    """Entrypoint que usan el router /engine/dispatch (F3b) y /engine/dispatch-manual (F3a). Resuelve
    el bot + versión vigente, elige el engine (engine_factory por el provider) y corre el turno. Las
    excepciones de dominio (CONVERSATION_NOT_BOT / NO_CURRENT_VERSION / PROVIDER_NOT_SUPPORTED) se
    propagan (visibles en el dispatch-manual). Los errores de provider/red se capturan como
    BotEvent(turn_failed) + fallback; el turno NO devuelve 5xx (no spamear reintentos)."""
    from app.modules.bots.services.engine import engine_factory

    try:
        conv = await conversation_repository.get_by_id(db, conversation_id)
        if conv is None:
            raise NotFoundException("Conversación no encontrada", code="CONVERSATION_NOT_FOUND")
        config = await choose_bot_for_conversation(db, conv)
        if config is None or config.current_version_id is None:
            raise BadRequestException("El bot no tiene versión vigente", code="NO_CURRENT_VERSION")
        version = await bot_configuration_version_repository.get_by_id(
            db, config.current_version_id
        )
        if version is None:
            raise BadRequestException("El bot no tiene versión vigente", code="NO_CURRENT_VERSION")
        engine = engine_factory(version)  # EmbeddedBotEngine | PROVIDER_NOT_SUPPORTED
        await engine.dispatch_turn(
            db, conversation_id=conversation_id, input_message_id=input_message_id
        )
    except (BadRequestException, NotFoundException):
        raise  # CONVERSATION_NOT_BOT / NO_CURRENT_VERSION / PROVIDER_NOT_SUPPORTED → 400/404 visible
    except Exception as exc:  # noqa: BLE001 — provider/red → turn_failed + fallback, sin 5xx
        logger.warning(
            "bot turn failed", extra={"conversation_id": conversation_id, "error": str(exc)}
        )
        await _log_turn_failed(db, conversation_id, error=str(exc))
