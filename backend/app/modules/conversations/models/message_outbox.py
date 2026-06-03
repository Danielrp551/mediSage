"""
MessageOutbox = cola transaccional durable Postgres→Firestore (Transactional Outbox,
ADR-011). Resuelve el dual-write Postgres↔Firestore SIN transacción distribuida: la TX
del control plane escribe aquí (misma tx, atómico) y un relay aparte la replica a
Firestore con el Admin SDK y la marca `done`. SIN SoftDeleteMixin (es infraestructura,
no entidad de negocio).

El `id` ES el `mid` del mensaje (`wamid` inbound / `uuid` outbound) → UNIQUE (es PK) da
idempotencia: el `INSERT ... ON CONFLICT (id) DO NOTHING` deduplica el reenvío del
webhook de Meta, y el mismo `mid` es el doc-id en Firestore (`set` create-if-absent) →
doble dedup. El `unread_count++` solo corre si el insert fue nuevo. Para
`op=conversation_upsert` (sin mid de mensaje) el `id` es un uuid sintético; lo que
importa ahí es el `conversation_id` del payload (doc-id Firestore = cid, idempotente
por overwrite).

NB: NO hereda `PrimaryKeyMixin` (que fuerza `varchar(36)` + autogen `uuid`): el `id` es
el `mid` (varchar(255) — el wamid de Meta es más largo que un uuid) y lo provee el
caller, nunca se autogenera. `op` distingue message_create / message_status /
conversation_upsert. `payload` (JSONB variant) = el doc EXACTO a escribir en Firestore.
Índice (status, created_on) para que el relay barra los pendientes en orden.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import ActiveMixin, TimestampMixin


class MessageOutbox(ActiveMixin, TimestampMixin, Base):
    __tablename__ = "message_outbox"
    __table_args__ = (
        # El relay barre los pendientes en orden de llegada.
        Index("ix_message_outbox_status_created", "status", "created_on"),
    )

    # = mid (wamid inbound / uuid outbound). PROVISTO por el caller (no autogen) → PK
    # UNIQUE = idempotencia (ON CONFLICT (id) DO NOTHING). varchar(255) para el wamid.
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id"), nullable=False, index=True
    )
    # message_create | message_status | conversation_upsert
    op: Mapped[str] = mapped_column(String(40), nullable=False)
    # El doc EXACTO a escribir en Firestore (snake_case, mismo shape que MessageItem /
    # el conversation doc). JSON en sqlite (smoke), JSONB en Postgres.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    # pending | done | failed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
