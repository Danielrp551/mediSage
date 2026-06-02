"""Repositorios del módulo `conversations` (skeleton F0, inerte).

Extienden `BaseRepository[Model]` y definen `ALLOWED_FIELDS` como whitelist
estricta de columnas REALES (lección hotfix `cd10c78` de staff: los campos
denormalizados —person full_name, channel name, assignee, preview— NO son
sortable/filterable server-side). La denormalización va por batch maps sin N+1
(patrón crm). Se introducen por fases (F1: channel_account; F2: conversation +
message + attachment + assignment_log). F0 no declara repositorios todavía.
"""
