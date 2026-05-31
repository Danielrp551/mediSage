"""staff: doctor_availability (bloques concretos por fecha)

Revision ID: 0010_staff_doctor_availability
Revises: 0009_staff_doctor
Create Date: 2026-05-30 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_staff_doctor_availability"
down_revision: str | None = "0009_staff_doctor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor_availability",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("doctor_id", sa.String(length=36), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branch.id"), nullable=False),
        sa.Column("office_id", sa.String(length=36), sa.ForeignKey("office.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "closes_at > opens_at", name="ck_doctor_availability_closes_after_opens"
        ),
    )
    op.create_index("ix_doctor_availability_doctor_id", "doctor_availability", ["doctor_id"])
    op.create_index(
        "ix_doctor_availability_doctor_id_date",
        "doctor_availability",
        ["doctor_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_doctor_availability_doctor_id_date", table_name="doctor_availability")
    op.drop_index("ix_doctor_availability_doctor_id", table_name="doctor_availability")
    op.drop_table("doctor_availability")
