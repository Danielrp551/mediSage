"""
Importar los modelos aquí asegura que SQLAlchemy los registre en
`Base.metadata` antes de que Alembic lea el esquema. Importar associations
primero para que las tablas M:N existan antes de que Doctor las referencie.

Orden: associations → Doctor → DoctorAvailability.
"""

from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.modules.staff.models.doctor import Doctor
from app.modules.staff.models.doctor_availability import DoctorAvailability

__all__ = [
    "Doctor",
    "DoctorAvailability",
    "doctor_branch",
    "doctor_vertical",
]
