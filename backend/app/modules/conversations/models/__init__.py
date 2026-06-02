"""Modelos SQLAlchemy del módulo `conversations` (skeleton F0, inerte).

Importar los modelos aquí registrará cada entidad en `Base.metadata` antes de que
Alembic lea el esquema y antes de resolver los `relationship(...)` por string.
Orden: padres (`channel_account`) antes que hijos (`conversation` → `message` →
`message_attachment`, `conversation_assignment_log`).

⚠ Subset por fases (ver `docs/modules/conversations/backend.md`):
- F1: `ChannelAccount`.
- F2: `Conversation`, `Message`, `MessageAttachment`,
  `ConversationAssignmentLog`.

`Message`/`MessageAttachment`/`ConversationAssignmentLog` NO llevan
`SoftDeleteMixin` (audit trail inmutable). F0 no declara modelos todavía.
"""
