"""
Tablas de asociación M:N del módulo staff. En un solo archivo para que
SQLAlchemy las vea antes de los modelos que las referencian (convención del
template — admin/models/associations.py y clinic/models/associations.py igual).

`doctor_branch` liga un Doctor a las Sedes (clinic.Branch) donde atiende.
`doctor_vertical` liga un Doctor a las Verticales (catalog.Vertical) que cubre.

Misma política de FK que clinic.office_vertical: el lado HIJO (doctor_id) es
ON DELETE CASCADE — el soft-delete del doctor es el path normal (se filtra al
consultar), pero un hard-delete de un doctor puede limpiar sus filas de
asociación sin coordinación cross-module. El lado PADRE externo (branch_id /
vertical_id) es RESTRICT (default, sin ondelete) — la sede/vertical se borra
desde SU propio módulo; la FK es el backstop que bloquea un hard-delete mientras
siga asociada. El soft-delete normal de una sede/vertical NO toca estas tablas:
las filas quedan y se filtran al hidratar (ver el repositorio).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

doctor_branch = Table(
    "doctor_branch",
    Base.metadata,
    Column(
        "doctor_id",
        String(36),
        ForeignKey("doctor.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "branch_id",
        String(36),
        ForeignKey("branch.id"),  # RESTRICT — sin cascade hacia clinic
        primary_key=True,
    ),
)

doctor_vertical = Table(
    "doctor_vertical",
    Base.metadata,
    Column(
        "doctor_id",
        String(36),
        ForeignKey("doctor.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "vertical_id",
        String(36),
        ForeignKey("vertical.id"),  # RESTRICT — sin cascade hacia catalog
        primary_key=True,
    ),
)
