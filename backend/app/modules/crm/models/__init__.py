"""
Importar los modelos aquí asegura que SQLAlchemy los registre en
`Base.metadata` antes de que Alembic lea el esquema y antes de que se resuelvan
los `relationship(...)` por string. Orden: padres (person) antes que hijos
(person_contact_identifier).

⚠ F1 subset: solo Person + PersonContactIdentifier. Las otras 10 entidades
(catálogos, lifecycle, assignment, activity) entran en F2–F5 — ver
`docs/modules/crm/backend.md`.
"""

from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier

__all__ = [
    "Person",
    "PersonContactIdentifier",
]
