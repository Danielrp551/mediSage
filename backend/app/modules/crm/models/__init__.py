"""
Importar los modelos aquí asegura que SQLAlchemy los registre en
`Base.metadata` antes de que Alembic lea el esquema y antes de que se resuelvan
los `relationship(...)` por string. Orden: padres (person, catálogos) antes que
hijos (identifiers, transiciones que FK a los catálogos).

⚠ Subset por fases: F1 = Person + PersonContactIdentifier; F2 = LeadStatus /
CustomerStatus + las dos tablas de transición. Lifecycle/assignment/activity
(F3–F5) NO se referencian todavía (modelos inexistentes romperían el mapper) —
ver `docs/modules/crm/backend.md`.
"""

from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.customer_status_transition import CustomerStatusTransition
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_transition import LeadStatusTransition
from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier

__all__ = [
    "Person",
    "PersonContactIdentifier",
    "LeadStatus",
    "CustomerStatus",
    "LeadStatusTransition",
    "CustomerStatusTransition",
]
