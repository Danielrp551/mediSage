"""
Importar los modelos aquí registra cada entidad en `Base.metadata` antes de que
Alembic lea el esquema y antes de resolver los `relationship(...)` por string.
Orden: padres (`channel_account`) antes que hijos (`conversation` →
`message_outbox`, `conversation_assignment_log`).

⚠ Subset por fases (ver `docs/modules/conversations/backend.md`):
- F1: `ChannelAccount`.
- F2: `Conversation`, `MessageOutbox`, `ConversationAssignmentLog`.

NB (CQRS / ADR-011): el stream de mensajes NO es Postgres — vive en Firestore como
read-model. NO hay `Message` ni `MessageAttachment` acá; lo que se registra en F2
es `message_outbox` (cola transaccional Postgres→Firestore). `MessageOutbox` /
`ConversationAssignmentLog` NO llevan `SoftDeleteMixin` (cola durable / audit trail
inmutable).
"""

from app.modules.conversations.models.channel_account import ChannelAccount

__all__ = [
    "ChannelAccount",
]
