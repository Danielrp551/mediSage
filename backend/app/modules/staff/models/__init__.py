"""
Importar los modelos aquí asegura que SQLAlchemy los registre en
`Base.metadata` antes de que Alembic lea el esquema. Importar associations
primero para que las tablas M:N existan antes de que Doctor las referencie.

`DoctorAvailability` se agrega en F2.
"""

from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.modules.staff.models.doctor import Doctor

__all__ = [
    "Doctor",
    "doctor_branch",
    "doctor_vertical",
]
