"""
Importar los modelos aquí asegura que SQLAlchemy los registre en
`Base.metadata` antes de que Alembic lea el esquema y antes de que se resuelvan
los `relationship(...)` por string. Orden: padres (person, catálogos) antes que
hijos (identifiers, transiciones que FK a los catálogos).

⚠ Subset por fases: F1 = Person + PersonContactIdentifier; F2 = LeadStatus /
CustomerStatus + las dos tablas de transición; F3 = lead lifecycle
(PersonLeadStatus, LeadStatusHistory, LeadAssignment, LeadActivity); **F4 = customer
lifecycle** (PersonCustomerStatus, CustomerStatusHistory) — ver
`docs/modules/crm/backend.md`.
"""

from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.customer_status_history import CustomerStatusHistory
from app.modules.crm.models.customer_status_transition import CustomerStatusTransition
from app.modules.crm.models.lead_activity import LeadActivity
from app.modules.crm.models.lead_assignment import LeadAssignment
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_history import LeadStatusHistory
from app.modules.crm.models.lead_status_transition import LeadStatusTransition
from app.modules.crm.models.person import Person
from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.crm.models.person_lead_status import PersonLeadStatus

__all__ = [
    "Person",
    "PersonContactIdentifier",
    "LeadStatus",
    "CustomerStatus",
    "LeadStatusTransition",
    "CustomerStatusTransition",
    "PersonLeadStatus",
    "LeadStatusHistory",
    "LeadAssignment",
    "LeadActivity",
    "PersonCustomerStatus",
    "CustomerStatusHistory",
]
