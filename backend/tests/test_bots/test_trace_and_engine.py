"""
Tests del módulo bots — panel de depuración (state/events/tool-calls), reset, y el motor (engine
factory + helpers puros + ramas de validación de `dispatch_turn`).

Los endpoints de traza necesitan filas reales (ConversationBotState / BotEvent / BotToolCall) que NO
se crean por API (las escribe el engine en runtime). Se siembran directamente en la BD de test vía el
fixture `db_session`, que comparte el mismo engine in-memory que `client` (ambos cuelgan de
`session_factory`). Para el motor se cubren: `engine_factory` (openai/claude → Embedded;
vertex_ai → PROVIDER_NOT_SUPPORTED), los helpers puros de `embedded.py`, y las ramas de validación
de `dispatch_turn` (404/400) que NO requieren LLM ni Firestore.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.utils import generate_uuid, utc_now

PREFIX = "/api/v1/bots"
CONV_PREFIX = "/api/v1/conversations"


async def _token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post("/api/v1/admin/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, admin_credentials)}"}


# ── Helpers de siembra directa (control plane) ───────────────────────────


async def _seed_config_and_version(db: AsyncSession, actor_id: str) -> tuple[str, str]:
    from app.modules.bots.models.bot_configuration import BotConfiguration
    from app.modules.bots.models.bot_configuration_version import BotConfigurationVersion

    now = utc_now()
    cfg = BotConfiguration(
        id=generate_uuid(),
        code=f"trace_bot_{generate_uuid()[:8]}",
        name="Bot traza",
        bot_type="general",
        description=None,
        current_version_id=None,
        max_turns_per_conversation=None,
        active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(cfg)
    await db.flush()
    ver = BotConfigurationVersion(
        id=generate_uuid(),
        bot_configuration_id=cfg.id,
        version=1,
        system_prompt="hola",
        provider="openai",
        model_name="gpt-4.1-mini",
        parameters={},
        external_webhook_url=None,
        external_webhook_secret_name=None,
        notes=None,
        active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(ver)
    await db.flush()
    cfg.current_version_id = ver.id
    await db.flush()
    return cfg.id, ver.id


async def _seed_channel_account(db: AsyncSession, actor_id: str) -> str:
    from app.modules.conversations.models.channel_account import ChannelAccount

    now = utc_now()
    ca = ChannelAccount(
        id=generate_uuid(),
        channel_type="whatsapp",
        name="WA test",
        external_identifier=f"ext_{generate_uuid()[:8]}",
        secret_name=None,
        webhook_verify_token=None,
        phone_number_id=None,
        active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(ca)
    await db.flush()
    return ca.id


async def _seed_conversation(
    db: AsyncSession,
    actor_id: str,
    *,
    assignee_type: str = "bot",
    status: str = "open",
    bot_configuration_id: str | None = None,
) -> str:
    from app.modules.conversations.models.conversation import Conversation

    ca_id = await _seed_channel_account(db, actor_id)
    now = utc_now()
    conv = Conversation(
        id=generate_uuid(),
        channel_account_id=ca_id,
        person_id=None,
        status=status,
        assignee_type=assignee_type,
        assignee_user_id=None,
        bot_configuration_id=bot_configuration_id,
        opened_at=now,
        closed_at=None,
        last_message_at=None,
        last_message_preview=None,
        unread_count=0,
        active=True,
        created_by=actor_id, created_on=now, updated_by=actor_id, updated_on=now,
    )
    db.add(conv)
    await db.flush()
    return conv.id


# ── get_state / reset_state ──────────────────────────────────────────────


async def test_get_state_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/conversations/no-conv/state", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_STATE_NOT_FOUND"


async def test_get_and_reset_state(
    client: AsyncClient, admin_credentials: dict, db_session: AsyncSession
) -> None:
    headers = await _headers(client, admin_credentials)
    from app.modules.bots.models.conversation_bot_state import ConversationBotState
    from app.modules.crm.services.person import SYSTEM_USER_ID

    cfg_id, ver_id = await _seed_config_and_version(db_session, SYSTEM_USER_ID)
    conv_id = await _seed_conversation(db_session, SYSTEM_USER_ID, bot_configuration_id=cfg_id)
    now = utc_now()
    state = ConversationBotState(
        id=generate_uuid(),
        conversation_id=conv_id,
        bot_configuration_id=cfg_id,
        bot_configuration_version_id=ver_id,
        current_intent="agendar",
        collected_slots={"fecha": "lunes"},
        last_node="ask_date",
        last_bot_turn_at=now,
        turn_count=3,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db_session.add(state)
    await db_session.commit()

    # GET state — denormaliza code + version_number
    r = await client.get(f"{PREFIX}/conversations/{conv_id}/state", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["conversation_id"] == conv_id
    assert data["current_intent"] == "agendar"
    assert data["collected_slots"] == {"fecha": "lunes"}
    assert data["turn_count"] == 3
    assert data["version_number"] == 1

    # RESET state — limpia slots/intent/turn_count
    rr = await client.post(
        f"{PREFIX}/conversations/{conv_id}/state/reset",
        json={"reason": "QA"},
        headers=headers,
    )
    assert rr.status_code == 200, rr.text
    reset = rr.json()["data"]
    assert reset["collected_slots"] == {}
    assert reset["current_intent"] is None
    assert reset["last_node"] is None
    assert reset["turn_count"] == 0
    assert reset["bot_configuration_version_id"] == ver_id  # re-fija la vigente


async def test_reset_state_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/conversations/no-conv/state/reset", json={}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_STATE_NOT_FOUND"


# ── events / tool-calls (lista vacía sin 404; con datos sembrados) ───────


async def test_list_events_empty(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/conversations/whatever/events", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_list_tool_calls_empty(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/conversations/whatever/tool-calls", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_list_events_and_tool_calls_with_data(
    client: AsyncClient, admin_credentials: dict, db_session: AsyncSession
) -> None:
    headers = await _headers(client, admin_credentials)
    from decimal import Decimal

    from app.modules.bots.models.bot_event import BotEvent
    from app.modules.bots.models.bot_tool import BotTool
    from app.modules.bots.models.bot_tool_call import BotToolCall
    from app.modules.crm.services.person import SYSTEM_USER_ID

    cfg_id, ver_id = await _seed_config_and_version(db_session, SYSTEM_USER_ID)
    conv_id = await _seed_conversation(db_session, SYSTEM_USER_ID, bot_configuration_id=cfg_id)
    now = utc_now()
    event = BotEvent(
        id=generate_uuid(),
        conversation_id=conv_id,
        bot_configuration_id=cfg_id,
        bot_configuration_version_id=ver_id,
        turn_number=1,
        event_type="turn_completed",
        input_message_id="mid-in",
        output_message_id="mid-out",
        tokens_in=10,
        tokens_out=5,
        latency_ms=120,
        cost_estimated_usd=Decimal("0.000012"),
        error=None,
        event_metadata={"provider": "openai"},
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db_session.add(event)
    tool = BotTool(
        id=generate_uuid(),
        code=f"trace_tool_{generate_uuid()[:8]}",
        name="Trace tool",
        description="x",
        parameters_schema={},
        target_service="crm.person.find",
        requires_confirmation=False,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db_session.add(tool)
    await db_session.flush()
    call = BotToolCall(
        id=generate_uuid(),
        conversation_id=conv_id,
        bot_event_id=event.id,
        bot_tool_id=tool.id,
        tool_use_id="tu-1",
        arguments={"q": "hola"},
        result={"ok": True},
        status="success",
        error_message=None,
        started_at=now,
        completed_at=now,
        latency_ms=42,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db_session.add(call)
    await db_session.commit()

    re = await client.get(f"{PREFIX}/conversations/{conv_id}/events", headers=headers)
    assert re.status_code == 200, re.text
    events = re.json()["data"]
    assert len(events) == 1
    assert events[0]["event_type"] == "turn_completed"
    assert events[0]["metadata"] == {"provider": "openai"}
    assert events[0]["tokens_in"] == 10

    rt = await client.get(f"{PREFIX}/conversations/{conv_id}/tool-calls", headers=headers)
    assert rt.status_code == 200, rt.text
    calls = rt.json()["data"]
    assert len(calls) == 1
    assert calls[0]["status"] == "success"
    assert calls[0]["bot_tool_code"] == tool.code  # denormalizado
    assert calls[0]["arguments"] == {"q": "hola"}


# ── engine_factory ───────────────────────────────────────────────────────


def test_engine_factory_openai_returns_embedded() -> None:
    from app.modules.bots.services.engine import engine_factory
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    class _V:
        provider = "openai"

    assert isinstance(engine_factory(_V()), EmbeddedBotEngine)


def test_engine_factory_claude_returns_embedded() -> None:
    from app.modules.bots.services.engine import engine_factory
    from app.modules.bots.services.engine.embedded import EmbeddedBotEngine

    class _V:
        provider = "claude"

    assert isinstance(engine_factory(_V()), EmbeddedBotEngine)


def test_engine_factory_unsupported_provider_raises() -> None:
    from app.core.exceptions import BadRequestException
    from app.modules.bots.services.engine import engine_factory

    class _V:
        provider = "vertex_ai"

    with pytest.raises(BadRequestException) as exc:
        engine_factory(_V())
    assert exc.value.code == "PROVIDER_NOT_SUPPORTED"


# ── helpers puros de embedded.py ─────────────────────────────────────────


def test_estimate_cost_known_model() -> None:
    from app.modules.bots.services.engine.embedded import _estimate_cost

    cost = _estimate_cost("gpt-4.1-mini", 1_000_000, 0)
    assert str(cost) == "0.400000"


def test_estimate_cost_unknown_model_none() -> None:
    from app.modules.bots.services.engine.embedded import _estimate_cost

    assert _estimate_cost("modelo-inexistente", 100, 100) is None


def test_map_history_to_messages_roles_and_filter() -> None:
    from app.modules.bots.services.engine.embedded import _map_history_to_messages

    docs = [
        {"content": "hola", "content_type": "text", "direction": "inbound"},
        {"content": "buenas", "content_type": "text", "direction": "outbound"},
        {"content": "", "content_type": "text", "direction": "inbound"},  # vacío -> filtra
        {"content": "img", "content_type": "image", "direction": "inbound"},  # no texto -> filtra
    ]
    msgs = _map_history_to_messages(docs)
    assert msgs == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "buenas"},
    ]


def test_fallback_text_default_and_custom() -> None:
    from app.modules.bots.services.engine.embedded import _DEFAULT_FALLBACK, _fallback_text

    class _V:
        parameters = {"fallback_text": "Te ayudo en un momento"}

    class _V2:
        parameters = {}

    assert _fallback_text(_V()) == "Te ayudo en un momento"
    assert _fallback_text(_V2()) == _DEFAULT_FALLBACK


def test_tool_to_schema() -> None:
    from app.modules.bots.services.engine.embedded import _tool_to_schema

    class _T:
        code = "list_verticals"
        description = "Lista verticales"
        parameters_schema = {"type": "object", "properties": {}}

    schema = _tool_to_schema(_T())
    assert schema["name"] == "list_verticals"
    assert schema["description"] == "Lista verticales"


def test_assistant_and_tool_result_messages() -> None:
    from app.modules.bots.services.engine.embedded import (
        _assistant_message,
        _tool_result_message,
    )
    from app.modules.bots.services.engine.providers.openai import (
        ProviderResult,
        ProviderToolCall,
    )

    tc = ProviderToolCall(tool_use_id="tu-1", name="get_x", arguments={"a": 1})
    result = ProviderResult(text="ok", tool_calls=[tc], tokens_in=1, tokens_out=1)
    am = _assistant_message(result)
    assert am["role"] == "assistant"
    assert am["tool_calls"][0]["id"] == "tu-1"
    trm = _tool_result_message(tc, {"ok": True})
    assert trm["role"] == "tool"
    assert trm["tool_call_id"] == "tu-1"


def test_openai_tools_to_openai_helper() -> None:
    from app.modules.bots.services.engine.providers.openai import (
        OpenAIProvider,
        _tools_to_openai,
    )

    out = _tools_to_openai([{"name": "t1", "description": "d", "parameters": {"type": "object"}}])
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "t1"
    # construir el provider no llama a la API
    assert OpenAIProvider("gpt-4.1-mini").model == "gpt-4.1-mini"


# ── dispatch-manual: ramas de validación (sin LLM ni Firestore) ──────────


async def test_dispatch_manual_conversation_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Conversación inexistente → dispatch_turn lanza CONVERSATION_NOT_FOUND. El handler
    `dispatch-manual` (debugging, RBAC) NO envuelve en try/except (a diferencia de `/dispatch`,
    que mapea NotFound→503 para Cloud Tasks), así que la excepción de dominio sube al handler
    global → 404. Cubre el entrypoint `dispatch_turn` + la rama CONVERSATION_NOT_FOUND."""
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/engine/dispatch-manual",
        json={"conversation_id": "no-conv"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CONVERSATION_NOT_FOUND"


async def test_dispatch_manual_no_current_version_400(
    client: AsyncClient, admin_credentials: dict, db_session: AsyncSession
) -> None:
    """Conversación de bot con un bot SIN versión vigente → NO_CURRENT_VERSION (400)."""
    headers = await _headers(client, admin_credentials)
    from app.modules.bots.models.bot_configuration import BotConfiguration
    from app.modules.crm.services.person import SYSTEM_USER_ID

    now = utc_now()
    cfg = BotConfiguration(
        id=generate_uuid(),
        code=f"noverbot_{generate_uuid()[:8]}",
        name="Sin versión",
        bot_type="general",
        description=None,
        current_version_id=None,  # sin versión vigente
        max_turns_per_conversation=None,
        active=True,
        created_by=SYSTEM_USER_ID, created_on=now, updated_by=SYSTEM_USER_ID, updated_on=now,
    )
    db_session.add(cfg)
    await db_session.flush()
    conv_id = await _seed_conversation(db_session, SYSTEM_USER_ID, bot_configuration_id=cfg.id)
    await db_session.commit()

    r = await client.post(
        f"{PREFIX}/engine/dispatch-manual",
        json={"conversation_id": conv_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "NO_CURRENT_VERSION"


async def test_dispatch_manual_no_bot_assigned_400(
    client: AsyncClient, admin_credentials: dict, db_session: AsyncSession
) -> None:
    """Conversación sin bot_configuration_id → choose_bot devuelve None → NO_CURRENT_VERSION."""
    headers = await _headers(client, admin_credentials)
    from app.modules.crm.services.person import SYSTEM_USER_ID

    conv_id = await _seed_conversation(
        db_session, SYSTEM_USER_ID, bot_configuration_id=None
    )
    await db_session.commit()
    r = await client.post(
        f"{PREFIX}/engine/dispatch-manual",
        json={"conversation_id": conv_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "NO_CURRENT_VERSION"


async def test_dispatch_requires_secret_403(client: AsyncClient) -> None:
    """El endpoint interno /engine/dispatch usa shared-secret; sin header → 403."""
    r = await client.post(
        f"{PREFIX}/engine/dispatch", json={"conversation_id": "x"}
    )
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "BOT_DISPATCH_UNAUTHORIZED"


async def test_dispatch_manual_requires_permission(client: AsyncClient) -> None:
    r = await client.post(f"{PREFIX}/engine/dispatch-manual", json={"conversation_id": "x"})
    assert r.status_code in (401, 403), r.text


# ── clock tool (sin BD, determinística) ──────────────────────────────────


async def test_clock_tool_returns_datetime(db_session: AsyncSession) -> None:
    from app.modules.bots.services.engine.tools import BotInvocationContext
    from app.modules.bots.services.engine.tools.clock import get_current_datetime

    ctx = BotInvocationContext(
        conversation_id="c", person_id=None, bot_configuration_id="b", bot_tool_call_id="tc"
    )
    out = await get_current_datetime({}, ctx, db_session)
    assert "date" in out and "weekday" in out and "year" in out
    assert out["weekday"] in (
        "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"
    )
