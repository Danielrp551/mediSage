"""
Schema del dispatch del turno. Body de POST /engine/dispatch (target de Cloud Tasks, OIDC — F3b)
y de POST /engine/dispatch-manual (RBAC BOT_ENGINE_INVOKE, debugging — F3a). `input_message_id` =
el `mid` (doc-id Firestore) del inbound que disparó el turno (opcional: en el dispatch manual el
engine toma el último inbound del hilo desde Firestore si no se pasa).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DispatchTurnRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=36)
    input_message_id: str | None = Field(default=None, max_length=255)
