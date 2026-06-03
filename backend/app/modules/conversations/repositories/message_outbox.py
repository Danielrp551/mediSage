"""
MessageOutbox repository — la cola transaccional Postgres→Firestore (ADR-011). NO se
pagina ni filtra desde el front (`ALLOWED_FIELDS = set()`): es infraestructura interna.
La idempotencia inbound la da `enqueue` (ON CONFLICT (id) DO NOTHING en Postgres /
get-then-insert en sqlite), NO un get previo. Reemplaza a los (inexistentes) repos de
message/message_attachment (el stream vive en Firestore).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.models.message_outbox import MessageOutbox
from app.shared.base_repository import BaseRepository
from app.shared.utils import utc_now


class MessageOutboxRepository(BaseRepository[MessageOutbox]):
    ALLOWED_FIELDS: set[str] = set()  # infraestructura interna; nunca filtrable desde el front

    def __init__(self) -> None:
        super().__init__(MessageOutbox)

    async def enqueue(
        self,
        db: AsyncSession,
        *,
        id: str,
        conversation_id: str,
        op: str,
        payload: dict[str, Any],
        actor_id: str,
    ) -> bool:
        """Encola una operación durable. IDEMPOTENTE por PK: ON CONFLICT (id) DO NOTHING
        (Postgres). Devuelve True si insertó algo NUEVO, False si el id ya existía (reenvío
        de Meta dedup). El caller usa el bool para decidir si incrementa unread_count /
        actualiza last_message_* (solo en el insert nuevo). En sqlite (smoke) se emula con
        un get-then-insert (single-thread; sin carrera; el advisory lock de crm serializa
        por identifier en Postgres)."""
        now = utc_now()
        values = {
            "id": id,
            "conversation_id": conversation_id,
            "op": op,
            "payload": payload,
            "status": "pending",
            "attempts": 0,
            "active": True,
            "created_by": actor_id,
            "created_on": now,
            "updated_by": actor_id,
            "updated_on": now,
        }
        if db.bind.dialect.name == "postgresql":
            # ON CONFLICT DO NOTHING + RETURNING: devuelve la fila si insertó, nada si chocó
            # (reenvío de Meta dedup). scalar_one_or_none() → None ⇒ ya existía.
            stmt = (
                pg_insert(MessageOutbox)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[MessageOutbox.id])
                .returning(MessageOutbox.id)
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None
        # sqlite (smoke): get-then-insert; sin carrera (single-thread).
        existing = await db.get(MessageOutbox, id)
        if existing is not None:
            return False
        await db.execute(insert(MessageOutbox).values(**values))
        return True

    async def list_pending(self, db: AsyncSession, *, limit: int = 100) -> list[MessageOutbox]:
        """El relay barre los pendientes por (status, created_on)."""
        result = await db.execute(
            select(MessageOutbox)
            .where(MessageOutbox.status == "pending")
            .order_by(MessageOutbox.created_on.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_done(self, db: AsyncSession, outbox_id: str) -> None:
        await db.execute(
            update(MessageOutbox)
            .where(MessageOutbox.id == outbox_id)
            .values(status="done", processed_on=utc_now())
        )

    async def mark_failed(self, db: AsyncSession, outbox_id: str, *, error: str) -> None:
        await db.execute(
            update(MessageOutbox)
            .where(MessageOutbox.id == outbox_id)
            .values(
                status="failed",
                attempts=MessageOutbox.attempts + 1,
                last_error=error[:500],
                processed_on=utc_now(),
            )
        )


message_outbox_repository = MessageOutboxRepository()
