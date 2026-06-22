"""
Tests del MOTOR del bot (`EmbeddedBotEngine.dispatch_turn` + entrypoint `dispatch_turn`), corriendo
un turno completo con Firestore y el provider del LLM MONKEYPATCHEADOS (sin red).

Se ejecutan EN EL HILO DEL TEST (llamada directa al service con `db_session`), de modo que el código
async del motor queda instrumentado por coverage sin depender de la traza de hilos del cliente ASGI.
Cubren: respuesta de texto simple, el loop de tool-calling (tool registrada que se ejecuta + tool
NO asignada + tool sin función en el registry), el guard de max_turns, y las ramas de validación
(CONVERSATION_NOT_BOT / CONVERSATION_NOT_OPEN / NO_CURRENT_VERSION / idempotencia / turn_failed).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.utils import generate_uuid, utc_now

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000002"


# ── Fakes del provider + Firestore + outbound ────────────────────────────


class _FakeResult:
    def __init__(self, text=None, tool_calls=None, tokens_in=3, tokens_out=2):
        self.text = text
        self.tool_calls = tool_calls or []
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.raw = {}


def _make_fake_adapter(script):
    """script = lista de _FakeResult, uno por iteración del loop de tool-calling."""
    calls = {"i": 0}

    class _FakeAdapter:
        def __init__(self, model):
            self.model = model

        async def complete(self, *, system, messages, tools, params):
            i = calls["i"]
            calls["i"] += 1
            return script[min(i, len(script) - 1)]

    return _FakeAdapter


class _FakeSent:
    class _Data:
        id = "out-mid-123"

    data = _Data()


async def _fake_send_bot_outbound(db, conv, text, *, bot_configuration_id):
    return _FakeSent()


def _patch_common(monkeypatch, *, history=None, adapter=None):
    from app.core import firestore
    from app.modules.bots.services.engine import embedded
    from app.modules.conversations.services import message as conv_message

    monkeypatch.setattr(
        firestore, "list_message_docs", lambda cid, *, skip, limit: (history or [], 0)
    )
    monkeypatch.setattr(conv_message, "send_bot_outbound", _fake_send_bot_outbound)
    if adapter is not None:
        monkeypatch.setitem(embedded._PROVIDER_ADAPTERS, _provider_openai(), adapter)


def _provider_openai():
    from app.modules.bots.enums import BotProvider

    return BotProvider.openai


# ── Helpers de siembra ───────────────────────────────────────────────────


async def _seed_bot(db: AsyncSession, *, max_turns=None) -> tuple[str, str]:
    from app.modules.bots.models.bot_configuration import BotConfiguration
    from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion

    now = utc_now()
    cfg = BotConfiguration(
        id=generate_uuid(),
        code=f"eng_{generate_uuid()[:8]}",
        name="Bot motor",
        bot_type="general",
        description=None,
        current_version_id=None,
        max_turns_per_conversation=max_turns,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db.add(cfg)
    await db.flush()
    ver = BotConfigurationVersion(
        id=generate_uuid(),
        bot_configuration_id=cfg.id,
        version=1,
        system_prompt="Eres un asistente.",
        provider="openai",
        model_name="gpt-4.1-mini",
        parameters={"temperature": 0.1},
        external_webhook_url=None,
        external_webhook_secret_name=None,
        notes=None,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db.add(ver)
    await db.flush()
    cfg.current_version_id = ver.id
    await db.flush()
    return cfg.id, ver.id


async def _seed_conversation(
    db: AsyncSession, *, bot_id, assignee_type="bot", status="open"
) -> str:
    from app.modules.conversations.models.channel_account import ChannelAccount
    from app.modules.conversations.models.conversation import Conversation

    now = utc_now()
    ca = ChannelAccount(
        id=generate_uuid(),
        channel_type="whatsapp",
        name="WA",
        external_identifier=f"e_{generate_uuid()[:8]}",
        secret_name=None,
        webhook_verify_token=None,
        phone_number_id=None,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db.add(ca)
    await db.flush()
    conv = Conversation(
        id=generate_uuid(),
        channel_account_id=ca.id,
        person_id=None,
        status=status,
        assignee_type=assignee_type,
        assignee_user_id=None,
        bot_configuration_id=bot_id,
        opened_at=now,
        closed_at=None,
        last_message_at=None,
        last_message_preview=None,
        unread_count=0,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db.add(conv)
    await db.flush()
    return conv.id


async def _assign_tool(db: AsyncSession, bot_id: str, *, code: str, name: str) -> str:
    from sqlalchemy import insert

    from app.modules.bots.models.associations import bot_configuration_tool
    from app.modules.bots.models.bot_tool import BotTool

    now = utc_now()
    tool = BotTool(
        id=generate_uuid(),
        code=code,
        name=name,
        description="tool de prueba",
        parameters_schema={"type": "object", "properties": {}},
        target_service="x.y.z",
        requires_confirmation=False,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db.add(tool)
    await db.flush()
    await db.execute(
        insert(bot_configuration_tool).values(
            bot_configuration_id=bot_id, bot_tool_id=tool.id
        )
    )
    await db.flush()
    return tool.id


# ── Turno: respuesta de texto simple (sin tools) ─────────────────────────


async def test_dispatch_turn_text_only(db_session: AsyncSession, monkeypatch) -> None:
    from app.modules.bots.repositories.bot_event import bot_event_repository
    from app.modules.bots.repositories.conversation_bot_state import (
        conversation_bot_state_repository,
    )
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    _patch_common(
        monkeypatch,
        history=[{"content": "hola", "content_type": "text", "direction": "inbound"}],
        adapter=_make_fake_adapter([_FakeResult(text="¡Hola! ¿En qué te ayudo?")]),
    )

    await EmbeddedBotEngine().dispatch_turn(
        db_session, conversation_id=conv_id, input_message_id="in-1"
    )

    # estado creado + turno contado
    state = await conversation_bot_state_repository.get_by_conversation(db_session, conv_id)
    assert state is not None
    assert state.turn_count == 1
    # eventos: turn_started + turn_completed
    events = await bot_event_repository.list_for_conversation(db_session, conv_id)
    types = {e.event_type for e in events}
    assert "turn_started" in types
    assert "turn_completed" in types


# ── Turno: loop de tool-calling con una tool registrada ──────────────────


async def test_dispatch_turn_with_registered_tool(
    db_session: AsyncSession, monkeypatch
) -> None:
    from app.modules.bots.repositories.bot_tool_call import bot_tool_call_repository
    from app.modules.bots.services.engine import tools as tools_pkg
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine
    from app.modules.bots.services.engine.providers.openai import ProviderToolCall

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    code = f"echo_tool_{generate_uuid()[:6]}"
    await _assign_tool(db_session, bot_id, code=code, name="Echo")

    # registrar una función para ese code en el TOOL_REGISTRY (se limpia al final)
    async def _echo(args, ctx, db):
        return {"ok": True, "echo": args.get("q")}

    monkeypatch.setitem(tools_pkg.TOOL_REGISTRY, code, _echo)

    # 1ª iteración: el LLM pide la tool; 2ª: responde texto final.
    script = [
        _FakeResult(
            tool_calls=[ProviderToolCall(tool_use_id="tu1", name=code, arguments={"q": "hi"})]
        ),
        _FakeResult(text="Listo, lo hice."),
    ]
    _patch_common(monkeypatch, history=[], adapter=_make_fake_adapter(script))

    await EmbeddedBotEngine().dispatch_turn(
        db_session, conversation_id=conv_id, input_message_id="in-2"
    )

    calls = await bot_tool_call_repository.list_for_conversation(db_session, conv_id)
    assert len(calls) == 1
    assert calls[0].status == "success"
    assert calls[0].result == {"ok": True, "echo": "hi"}


async def test_dispatch_turn_tool_not_registered(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Tool asignada al bot pero su code NO está en el TOOL_REGISTRY → BotToolCall con error."""
    from app.modules.bots.repositories.bot_tool_call import bot_tool_call_repository
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine
    from app.modules.bots.services.engine.providers.openai import ProviderToolCall

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    code = f"unreg_{generate_uuid()[:6]}"
    await _assign_tool(db_session, bot_id, code=code, name="NoReg")

    script = [
        _FakeResult(
            tool_calls=[ProviderToolCall(tool_use_id="tu1", name=code, arguments={})]
        ),
        _FakeResult(text="ok"),
    ]
    _patch_common(monkeypatch, history=[], adapter=_make_fake_adapter(script))

    await EmbeddedBotEngine().dispatch_turn(
        db_session, conversation_id=conv_id, input_message_id="in-3"
    )
    calls = await bot_tool_call_repository.list_for_conversation(db_session, conv_id)
    assert len(calls) == 1
    assert calls[0].status == "error"
    assert calls[0].error_message == "TOOL_NOT_REGISTERED"


async def test_dispatch_turn_tool_not_available(
    db_session: AsyncSession, monkeypatch
) -> None:
    """El LLM pide una tool que el bot NO tiene asignada → no se persiste BotToolCall, sigue el loop."""
    from app.modules.bots.repositories.bot_tool_call import bot_tool_call_repository
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine
    from app.modules.bots.services.engine.providers.openai import ProviderToolCall

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    script = [
        _FakeResult(
            tool_calls=[ProviderToolCall(tool_use_id="tu1", name="ghost_tool", arguments={})]
        ),
        _FakeResult(text="ok"),
    ]
    _patch_common(monkeypatch, history=[], adapter=_make_fake_adapter(script))

    await EmbeddedBotEngine().dispatch_turn(
        db_session, conversation_id=conv_id, input_message_id="in-4"
    )
    calls = await bot_tool_call_repository.list_for_conversation(db_session, conv_id)
    assert calls == []  # no hay bot_tool_id para persistir


async def test_dispatch_turn_tool_raises_is_captured(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Una tool que lanza excepción → BotToolCall status=error, el turno NO revienta."""
    from app.modules.bots.repositories.bot_tool_call import bot_tool_call_repository
    from app.modules.bots.services.engine import tools as tools_pkg
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine
    from app.modules.bots.services.engine.providers.openai import ProviderToolCall

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    code = f"boom_{generate_uuid()[:6]}"
    await _assign_tool(db_session, bot_id, code=code, name="Boom")

    async def _boom(args, ctx, db):
        raise ValueError("explotó la tool")

    monkeypatch.setitem(tools_pkg.TOOL_REGISTRY, code, _boom)
    script = [
        _FakeResult(
            tool_calls=[ProviderToolCall(tool_use_id="tu1", name=code, arguments={})]
        ),
        _FakeResult(text="seguimos"),
    ]
    _patch_common(monkeypatch, history=[], adapter=_make_fake_adapter(script))

    await EmbeddedBotEngine().dispatch_turn(
        db_session, conversation_id=conv_id, input_message_id="in-5"
    )
    calls = await bot_tool_call_repository.list_for_conversation(db_session, conv_id)
    assert len(calls) == 1
    assert calls[0].status == "error"
    assert "explotó" in (calls[0].error_message or "")


# ── Guards / ramas de validación de EmbeddedBotEngine.dispatch_turn ──────


async def test_engine_conversation_not_bot(db_session: AsyncSession, monkeypatch) -> None:
    from app.core.exceptions import BadRequestException
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    bot_id, _ = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id, assignee_type="unassigned")
    _patch_common(monkeypatch)
    with pytest.raises(BadRequestException) as exc:
        await EmbeddedBotEngine().dispatch_turn(
            db_session, conversation_id=conv_id, input_message_id=None
        )
    assert exc.value.code == "CONVERSATION_NOT_BOT"


async def test_engine_conversation_not_open(db_session: AsyncSession, monkeypatch) -> None:
    from app.core.exceptions import BadRequestException
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    bot_id, _ = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id, status="closed")
    _patch_common(monkeypatch)
    with pytest.raises(BadRequestException) as exc:
        await EmbeddedBotEngine().dispatch_turn(
            db_session, conversation_id=conv_id, input_message_id=None
        )
    assert exc.value.code == "CONVERSATION_NOT_OPEN"


async def test_engine_conversation_not_found(db_session: AsyncSession, monkeypatch) -> None:
    from app.core.exceptions import NotFoundException
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    _patch_common(monkeypatch)
    with pytest.raises(NotFoundException) as exc:
        await EmbeddedBotEngine().dispatch_turn(
            db_session, conversation_id="ghost", input_message_id=None
        )
    assert exc.value.code == "CONVERSATION_NOT_FOUND"


async def test_engine_max_turns_cap(db_session: AsyncSession, monkeypatch) -> None:
    """turn_count >= max_turns_per_conversation → no llama al LLM, retorna silencioso."""
    from app.modules.bots.models.conversation_bot_state import ConversationBotState
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    bot_id, ver_id = await _seed_bot(db_session, max_turns=1)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    now = utc_now()
    db_session.add(
        ConversationBotState(
            id=generate_uuid(),
            conversation_id=conv_id,
            bot_configuration_id=bot_id,
            bot_configuration_version_id=ver_id,
            collected_slots={},
            turn_count=1,  # ya alcanzó el cap
            active=True,
            created_by=SYSTEM_USER_ID, created_on=now,
            updated_by=SYSTEM_USER_ID, updated_on=now,
        )
    )
    await db_session.flush()
    # adapter que reventaría si lo llamaran (no debe llamarse)
    _patch_common(monkeypatch, adapter=_make_fake_adapter([_FakeResult(text="x")]))
    await EmbeddedBotEngine().dispatch_turn(
        db_session, conversation_id=conv_id, input_message_id=None
    )  # no lanza, retorna silencioso


# ── entrypoint dispatch_turn (idempotencia + turn_failed) ────────────────


async def test_entrypoint_idempotent_skips_processed_input(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Si ya existe un BotEvent para el (conv, input_message_id), el entrypoint NO re-ejecuta."""
    from app.modules.bots.models.bot_event import BotEvent
    from app.modules.bots.services.engine.embedded import dispatch_turn

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    now = utc_now()
    db_session.add(
        BotEvent(
            id=generate_uuid(),
            conversation_id=conv_id,
            bot_configuration_id=bot_id,
            bot_configuration_version_id=ver_id,
            turn_number=1,
            event_type="turn_started",
            input_message_id="dup-input",
            active=True,
            created_by=SYSTEM_USER_ID, created_on=now,
            updated_by=SYSTEM_USER_ID, updated_on=now,
        )
    )
    await db_session.flush()

    from app.modules.bots.services.engine import embedded as embedded_mod

    called = {"n": 0}

    def _boom_adapter(model):
        called["n"] += 1
        raise AssertionError("no debió llamarse")

    _patch_common(monkeypatch)
    monkeypatch.setitem(embedded_mod._PROVIDER_ADAPTERS, _provider_openai(), _boom_adapter)
    # idempotente: retorna sin tocar el adapter
    await dispatch_turn(db_session, conversation_id=conv_id, input_message_id="dup-input")
    assert called["n"] == 0


async def test_entrypoint_no_current_version_propagates(
    db_session: AsyncSession, monkeypatch
) -> None:
    from app.core.exceptions import BadRequestException
    from app.modules.bots.models.bot_configuration import BotConfiguration
    from app.modules.bots.services.engine.embedded import dispatch_turn

    now = utc_now()
    cfg = BotConfiguration(
        id=generate_uuid(),
        code=f"nov_{generate_uuid()[:8]}",
        name="Sin versión",
        bot_type="general",
        description=None,
        current_version_id=None,
        max_turns_per_conversation=None,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db_session.add(cfg)
    await db_session.flush()
    conv_id = await _seed_conversation(db_session, bot_id=cfg.id)
    _patch_common(monkeypatch)
    with pytest.raises(BadRequestException) as exc:
        await dispatch_turn(db_session, conversation_id=conv_id, input_message_id=None)
    assert exc.value.code == "NO_CURRENT_VERSION"


async def test_entrypoint_provider_error_logs_turn_failed(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Un error de provider (no de dominio) se captura → turn_failed + fallback, sin re-lanzar."""
    from app.modules.bots.repositories.bot_event import bot_event_repository
    from app.modules.bots.services.engine.embedded import dispatch_turn

    bot_id, ver_id = await _seed_bot(db_session)
    conv_id = await _seed_conversation(db_session, bot_id=bot_id)
    # `_log_turn_failed` hace db.rollback() para escribir la traza sobre una sesión limpia → el
    # seed debe estar COMMITEADO para sobrevivir al rollback (sino la conv desaparece y no hay traza).
    await db_session.commit()

    class _BoomAdapter:
        def __init__(self, model):
            pass

        async def complete(self, *, system, messages, tools, params):
            raise RuntimeError("provider 500")

    _patch_common(monkeypatch, history=[], adapter=_BoomAdapter)

    # no debe re-lanzar (turn_failed se registra best-effort)
    await dispatch_turn(db_session, conversation_id=conv_id, input_message_id="in-fail")
    events = await bot_event_repository.list_for_conversation(db_session, conv_id)
    assert any(e.event_type == "turn_failed" for e in events)
