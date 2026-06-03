"""Repositorios del módulo `conversations`.

Extienden `BaseRepository[Model]` y definen `ALLOWED_FIELDS` como whitelist
estricta de columnas REALES (lección hotfix `cd10c78` de staff: los campos
denormalizados —person full_name, channel name, assignee, preview— NO son
sortable/filterable server-side). La denormalización va por batch maps sin N+1
(patrón crm). Se introducen por fases (F1: channel_account; F2: conversation +
message_outbox + assignment_log). NB (CQRS/ADR-011): NO hay repositorios de
`message`/`message_attachment` — el stream vive en Firestore; lo que aparece en F2
es `message_outbox` (cola transaccional).
"""
