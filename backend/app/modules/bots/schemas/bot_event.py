"""
Schema de BotEvent (traza por turno, read-only depuración). `cost_estimated_usd` es Decimal →
Pydantic v2 lo serializa como string en JSON (no perder precisión). `metadata` lo construye el
service desde el atributo `event_metadata` del modelo (la columna se llama "metadata").
`input/output_message_id` son el `mid` de Firestore (NO FK).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class BotEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    bot_configuration_id: str
    bot_configuration_version_id: str
    turn_number: int
    event_type: str
    input_message_id: str | None  # mid Firestore (NO FK)
    output_message_id: str | None
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    cost_estimated_usd: Decimal | None  # serializa como string en JSON
    error: str | None
    metadata: dict[str, Any] | None  # = event_metadata del modelo (lo mapea el service)
    created_on: datetime
