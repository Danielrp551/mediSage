"""
Tests de integración del módulo bots — BotConfiguration + versiones + activate-version + tools M:N.

Cubre los services `bot_configuration`, `bot_configuration_version` y la parte M:N de `bot_tool`
vía la API pública (fixture async `client`, admin con TODOS los permisos). Happy paths + bordes
(404, 409 código duplicado, 400 versión no perteneciente, validación 422).
"""

from __future__ import annotations

from httpx import AsyncClient

PREFIX = "/api/v1/bots"


async def _token(client: AsyncClient, admin_credentials: dict) -> str:
    r = await client.post("/api/v1/admin/auth/login", json=admin_credentials)
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


async def _headers(client: AsyncClient, admin_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, admin_credentials)}"}


def _config_payload(code: str = "preventa_bot", **over) -> dict:
    base = {
        "code": code,
        "name": "Bot Preventa",
        "bot_type": "preventa",
        "description": "Atiende preventa",
        "max_turns_per_conversation": 20,
    }
    base.update(over)
    return base


async def _create_config(client: AsyncClient, headers: dict, **over) -> dict:
    r = await client.post(f"{PREFIX}/configurations", json=_config_payload(**over), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ── BotConfiguration CRUD ────────────────────────────────────────────────


async def test_create_configuration(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    data = await _create_config(client, headers, code="bot_create")
    assert data["code"] == "bot_create"
    assert data["bot_type"] == "preventa"
    assert data["current_version_id"] is None  # sin versión todavía
    assert data["version_count"] == 0
    assert data["tool_ids"] == []
    assert data["active"] is True
    assert data["created_by_user"]["email"] == admin_credentials["email"]


async def test_create_configuration_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_config(client, headers, code="dup_bot")
    r = await client.post(
        f"{PREFIX}/configurations", json=_config_payload(code="dup_bot"), headers=headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_CODE_TAKEN"


async def test_create_configuration_invalid_code_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    # Mayúsculas + guiones no cumplen el patrón ^[a-z0-9_]+$.
    r = await client.post(
        f"{PREFIX}/configurations", json=_config_payload(code="Bad-Code"), headers=headers
    )
    assert r.status_code == 422, r.text


async def test_get_configuration(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_config(client, headers, code="bot_get")
    r = await client.get(f"{PREFIX}/configurations/{created['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]


async def test_get_configuration_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/configurations/nope-id", headers=headers)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_NOT_FOUND"


async def test_list_configurations_paginated(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_config(client, headers, code="bot_list_a")
    await _create_config(client, headers, code="bot_list_b")
    r = await client.post(
        f"{PREFIX}/configurations/list",
        json={"pagination": {"skip": 0, "limit": 50}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    codes = {i["code"] for i in data["items"]}
    assert {"bot_list_a", "bot_list_b"} <= codes
    assert data["total"] >= 2


async def test_list_configurations_filtered(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_config(client, headers, code="filtered_unique_bot")
    body = {
        "pagination": {"skip": 0, "limit": 10},
        "filters": {
            "filters": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "code", "operator": "eq", "value": "filtered_unique_bot"}
                    ],
                }
            ]
        },
    }
    r = await client.post(f"{PREFIX}/configurations/list", json=body, headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["code"] == "filtered_unique_bot"


async def test_list_active_configurations(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_config(client, headers, code="active_bot")
    r = await client.get(f"{PREFIX}/configurations/active", headers=headers)
    assert r.status_code == 200, r.text
    # /active devuelve una lista cruda (sin envelope).
    body = r.json()
    assert isinstance(body, list)
    assert any(c["code"] == "active_bot" for c in body)


async def test_update_configuration(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_config(client, headers, code="bot_upd")
    r = await client.put(
        f"{PREFIX}/configurations/{created['id']}",
        json={"name": "Nombre nuevo", "code": "bot_upd_2", "bot_type": "general"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Nombre nuevo"
    assert data["code"] == "bot_upd_2"
    assert data["bot_type"] == "general"


async def test_update_configuration_null_required_is_noop(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Un null explícito en una columna NOT NULL del Update parcial = "no cambiar"."""
    headers = await _headers(client, admin_credentials)
    created = await _create_config(client, headers, code="bot_noop")
    r = await client.put(
        f"{PREFIX}/configurations/{created['id']}",
        json={"code": None, "name": None, "bot_type": None, "active": None,
              "description": "solo desc"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["code"] == "bot_noop"  # no blanqueado
    assert data["name"] == "Bot Preventa"
    assert data["description"] == "solo desc"


async def test_update_configuration_duplicate_code_409(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    await _create_config(client, headers, code="bot_existing")
    other = await _create_config(client, headers, code="bot_other")
    r = await client.put(
        f"{PREFIX}/configurations/{other['id']}",
        json={"code": "bot_existing"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_CODE_TAKEN"


async def test_update_configuration_same_code_ok(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Re-enviar el MISMO code (clash con uno mismo) no debe disparar 409."""
    headers = await _headers(client, admin_credentials)
    created = await _create_config(client, headers, code="bot_same")
    r = await client.put(
        f"{PREFIX}/configurations/{created['id']}",
        json={"code": "bot_same", "name": "Renombrado"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Renombrado"


async def test_update_configuration_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(
        f"{PREFIX}/configurations/nope", json={"name": "x"}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_delete_configuration(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    created = await _create_config(client, headers, code="bot_del")
    r = await client.delete(f"{PREFIX}/configurations/{created['id']}", headers=headers)
    assert r.status_code == 204, r.text
    # tras soft-delete, ya no se encuentra
    r2 = await client.get(f"{PREFIX}/configurations/{created['id']}", headers=headers)
    assert r2.status_code == 404
    # el code queda liberado (UNIQUE parcial)
    r3 = await client.post(
        f"{PREFIX}/configurations", json=_config_payload(code="bot_del"), headers=headers
    )
    assert r3.status_code == 201, r3.text


async def test_delete_configuration_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.delete(f"{PREFIX}/configurations/nope", headers=headers)
    assert r.status_code == 404, r.text


# ── Versiones ────────────────────────────────────────────────────────────


def _version_payload(**over) -> dict:
    base = {
        "system_prompt": "Eres un asistente de la clínica.",
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "parameters": {"temperature": 0.2},
        "notes": "v inicial",
    }
    base.update(over)
    return base


async def test_create_first_version_becomes_current(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_ver1")
    r = await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions",
        json=_version_payload(),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    v = r.json()["data"]
    assert v["version"] == 1
    assert v["is_current"] is True  # primera versión = vigente automáticamente
    assert v["system_prompt"] == "Eres un asistente de la clínica."
    # el config ahora refleja la versión vigente
    rc = await client.get(f"{PREFIX}/configurations/{cfg['id']}", headers=headers)
    cfg_data = rc.json()["data"]
    assert cfg_data["current_version_id"] == v["id"]
    assert cfg_data["current_version_number"] == 1
    assert cfg_data["version_count"] == 1
    assert cfg_data["current_version"]["id"] == v["id"]


async def test_create_second_version_increments_not_current(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_ver2")
    await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions",
        json=_version_payload(), headers=headers,
    )
    r2 = await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions",
        json=_version_payload(notes="segunda"), headers=headers,
    )
    assert r2.status_code == 201, r2.text
    v2 = r2.json()["data"]
    assert v2["version"] == 2
    assert v2["is_current"] is False  # no promueve automáticamente la 2da


async def test_create_version_external_webhook_requires_url_422(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_ext")
    r = await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions",
        json=_version_payload(provider="external_webhook", external_webhook_url=None),
        headers=headers,
    )
    # El model_validator del schema lo rechaza como 422 (forma).
    assert r.status_code == 422, r.text


async def test_create_version_config_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/configurations/nope/versions", json=_version_payload(), headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_NOT_FOUND"


async def test_list_versions(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_listver")
    await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions", json=_version_payload(), headers=headers
    )
    await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions",
        json=_version_payload(notes="2"), headers=headers,
    )
    r = await client.get(f"{PREFIX}/configurations/{cfg['id']}/versions", headers=headers)
    assert r.status_code == 200, r.text
    versions = r.json()["data"]
    assert len(versions) == 2
    assert {v["version"] for v in versions} == {1, 2}


async def test_list_versions_config_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/configurations/nope/versions", headers=headers)
    assert r.status_code == 404, r.text


async def test_get_one_version(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_getver")
    vr = await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions", json=_version_payload(), headers=headers
    )
    vid = vr.json()["data"]["id"]
    r = await client.get(
        f"{PREFIX}/configurations/{cfg['id']}/versions/{vid}", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == vid
    assert "system_prompt" in r.json()["data"]


async def test_get_one_version_wrong_config_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg_a = await _create_config(client, headers, code="bot_va")
    cfg_b = await _create_config(client, headers, code="bot_vb")
    vr = await client.post(
        f"{PREFIX}/configurations/{cfg_a['id']}/versions",
        json=_version_payload(), headers=headers,
    )
    vid = vr.json()["data"]["id"]
    # versión existe pero pertenece a cfg_a → 404 al pedirla bajo cfg_b
    r = await client.get(
        f"{PREFIX}/configurations/{cfg_b['id']}/versions/{vid}", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_VERSION_NOT_FOUND"


async def test_get_one_version_config_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(
        f"{PREFIX}/configurations/nope/versions/whatever", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_NOT_FOUND"


# ── activate-version ─────────────────────────────────────────────────────


async def test_activate_version(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_act")
    await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/versions", json=_version_payload(), headers=headers
    )
    v2 = (
        await client.post(
            f"{PREFIX}/configurations/{cfg['id']}/versions",
            json=_version_payload(notes="2"), headers=headers,
        )
    ).json()["data"]
    r = await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/activate-version/{v2['id']}", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_version_id"] == v2["id"]
    assert r.json()["data"]["current_version_number"] == 2


async def test_activate_version_config_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/configurations/nope/activate-version/x", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_NOT_FOUND"


async def test_activate_version_version_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_actnf")
    r = await client.post(
        f"{PREFIX}/configurations/{cfg['id']}/activate-version/nope", headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_VERSION_NOT_FOUND"


async def test_activate_version_not_owned_400(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg_a = await _create_config(client, headers, code="bot_owna")
    cfg_b = await _create_config(client, headers, code="bot_ownb")
    v_a = (
        await client.post(
            f"{PREFIX}/configurations/{cfg_a['id']}/versions",
            json=_version_payload(), headers=headers,
        )
    ).json()["data"]
    # la versión de cfg_a no pertenece a cfg_b → 400 BOT_VERSION_NOT_OWNED
    r = await client.post(
        f"{PREFIX}/configurations/{cfg_b['id']}/activate-version/{v_a['id']}", headers=headers
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "BOT_VERSION_NOT_OWNED"


# ── Tools M:N (set / list por config) ────────────────────────────────────


async def _create_tool(client: AsyncClient, headers: dict, code: str) -> dict:
    r = await client.post(
        f"{PREFIX}/tools",
        json={
            "code": code,
            "name": f"Tool {code}",
            "description": "Una herramienta de prueba",
            "parameters_schema": {"type": "object", "properties": {}},
            "target_service": "crm.person.find",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_set_and_list_config_tools(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_tools")
    t1 = await _create_tool(client, headers, "tool_mn_one")
    t2 = await _create_tool(client, headers, "tool_mn_two")
    r = await client.put(
        f"{PREFIX}/configurations/{cfg['id']}/tools",
        json={"tool_ids": [t1["id"], t2["id"]]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["tool_ids"]) == {t1["id"], t2["id"]}
    # listado de tools del config
    rl = await client.get(f"{PREFIX}/configurations/{cfg['id']}/tools", headers=headers)
    assert rl.status_code == 200, rl.text
    assert {t["id"] for t in rl.json()["data"]} == {t1["id"], t2["id"]}


async def test_set_config_tools_replaces_set(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_tools_repl")
    t1 = await _create_tool(client, headers, "tool_repl_one")
    t2 = await _create_tool(client, headers, "tool_repl_two")
    await client.put(
        f"{PREFIX}/configurations/{cfg['id']}/tools",
        json={"tool_ids": [t1["id"]]}, headers=headers,
    )
    # reemplaza el set por solo t2
    r = await client.put(
        f"{PREFIX}/configurations/{cfg['id']}/tools",
        json={"tool_ids": [t2["id"]]}, headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tool_ids"] == [t2["id"]]


async def test_set_config_tools_empty(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_tools_empty")
    t1 = await _create_tool(client, headers, "tool_empty_one")
    await client.put(
        f"{PREFIX}/configurations/{cfg['id']}/tools",
        json={"tool_ids": [t1["id"]]}, headers=headers,
    )
    r = await client.put(
        f"{PREFIX}/configurations/{cfg['id']}/tools",
        json={"tool_ids": []}, headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tool_ids"] == []


async def test_set_config_tools_unknown_tool_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    cfg = await _create_config(client, headers, code="bot_tools_404")
    r = await client.put(
        f"{PREFIX}/configurations/{cfg['id']}/tools",
        json={"tool_ids": ["does-not-exist"]}, headers=headers,
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_TOOL_NOT_FOUND"


async def test_set_config_tools_config_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.put(
        f"{PREFIX}/configurations/nope/tools", json={"tool_ids": []}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "BOT_CONFIGURATION_NOT_FOUND"


async def test_list_config_tools_config_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await _headers(client, admin_credentials)
    r = await client.get(f"{PREFIX}/configurations/nope/tools", headers=headers)
    assert r.status_code == 404, r.text


# ── RBAC ─────────────────────────────────────────────────────────────────


async def test_requires_auth(client: AsyncClient) -> None:
    r = await client.post(
        f"{PREFIX}/configurations/list", json={"pagination": {"skip": 0, "limit": 10}}
    )
    assert r.status_code in (401, 403), r.text
