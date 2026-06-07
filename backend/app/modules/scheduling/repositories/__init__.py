"""
Repositorios del módulo `scheduling` (F1+), extienden `BaseRepository[Model]`. `ALLOWED_FIELDS`
SOLO columnas reales (lección cd10c78): los denormalizados (status code/color, doctor/person/office
names, etc.) NO son server-sortable/filterable. `appointment_status_transition_repository.is_allowed`
decide la legalidad de una transición. INERTE en F0.
"""
