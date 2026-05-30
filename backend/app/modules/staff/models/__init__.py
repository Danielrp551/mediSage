"""Modelos SQLAlchemy de `staff`.

Se poblará en F1+ importando los modelos aquí (como en `clinic.models`) para que
`Base.metadata` los registre antes de que Alembic lea el esquema: `associations`
(doctor_branch, doctor_vertical) → `Doctor` (F1) → `DoctorAvailability` (F2).
"""
