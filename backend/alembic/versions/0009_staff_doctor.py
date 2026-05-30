"""add staff doctor table + doctor_branch / doctor_vertical M:N

Revision ID: 0009_staff_doctor
Revises: 0008_clinic_office_closure
Create Date: 2026-05-30 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_staff_doctor"
down_revision: str | None = "0008_clinic_office_closure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # 1:1 con admin.User. RESTRICT (default): el User no se borra por borrar
        # el doctor (ADR-002). UNIQUE vía el índice único de abajo.
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("cmp_code", sa.String(length=40), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("signature_url", sa.String(length=500), nullable=True),
        sa.Column("slot_duration_min", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    # user_id es UNIQUE + indexado (1:1) — un índice único cubre ambas cosas.
    op.create_index("ix_doctor_user_id", "doctor", ["user_id"], unique=True)
    op.create_index("ix_doctor_cmp_code", "doctor", ["cmp_code"])

    # M:N doctor ↔ clinic.branch. doctor_id CASCADE (borrar un doctor puede
    # limpiar sus asociaciones); branch_id RESTRICT (backstop ante hard-delete de
    # una sede aún asociada — el soft-delete normal deja las filas y se filtran).
    op.create_table(
        "doctor_branch",
        sa.Column(
            "doctor_id",
            sa.String(length=36),
            sa.ForeignKey("doctor.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "branch_id",
            sa.String(length=36),
            sa.ForeignKey("branch.id"),
            primary_key=True,
        ),
    )

    # M:N doctor ↔ catalog.vertical. Misma política de FK.
    op.create_table(
        "doctor_vertical",
        sa.Column(
            "doctor_id",
            sa.String(length=36),
            sa.ForeignKey("doctor.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "vertical_id",
            sa.String(length=36),
            sa.ForeignKey("vertical.id"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("doctor_vertical")
    op.drop_table("doctor_branch")
    op.drop_index("ix_doctor_cmp_code", table_name="doctor")
    op.drop_index("ix_doctor_user_id", table_name="doctor")
    op.drop_table("doctor")
