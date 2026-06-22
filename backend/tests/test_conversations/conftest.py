"""
Fixtures locales de `test_conversations`. Mockea los writers de `app.core.firestore`
(el relay síncrono del outbox y el fallback de lectura los invocan; sin GCP reventarían)
y el `mint_custom_token` del real-time. Autouse: ningún test de conversations debe tocar
GCP. Las llamadas quedan registradas en `firestore_calls` para asserts opcionales.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core import firestore


@pytest.fixture(autouse=True)
def mock_firestore(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {
        "write_message_doc": [],
        "upsert_conversation_doc": [],
        "update_message_status": [],
        "list_message_docs": [],
        "mint_custom_token": [],
    }

    def _write_message_doc(conversation_id: str, doc: dict[str, Any]) -> None:
        calls["write_message_doc"].append((conversation_id, doc))

    def _upsert_conversation_doc(conversation_id: str, doc: dict[str, Any]) -> None:
        calls["upsert_conversation_doc"].append((conversation_id, doc))

    def _update_message_status(conversation_id: str | None, patch: dict[str, Any]) -> None:
        calls["update_message_status"].append((conversation_id, patch))

    def _list_message_docs(
        conversation_id: str, *, skip: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        calls["list_message_docs"].append((conversation_id, skip, limit))
        return [], 0

    def _mint_custom_token(uid: str, claims: dict[str, Any]) -> str:
        calls["mint_custom_token"].append((uid, claims))
        return f"fake-custom-token-{uid}"

    monkeypatch.setattr(firestore, "write_message_doc", _write_message_doc)
    monkeypatch.setattr(firestore, "upsert_conversation_doc", _upsert_conversation_doc)
    monkeypatch.setattr(firestore, "update_message_status", _update_message_status)
    monkeypatch.setattr(firestore, "list_message_docs", _list_message_docs)
    monkeypatch.setattr(firestore, "mint_custom_token", _mint_custom_token)
    return calls
