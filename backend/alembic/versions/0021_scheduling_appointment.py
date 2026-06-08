"""add scheduling appointment + status_history + change_log

Revision ID: 0021_scheduling_appointment
Revises: 0020_scheduling_status
Create Date: 2026-06-08 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_scheduling_appointment"
down_revision: str | None = "0020_scheduling_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Cita (PK·A·SD·T) — FKs reales (las tablas existen) + self-FK. ──
    op.create_table(
        "appointment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("office_id", sa.String(length=36), sa.ForeignKey("office.id"), nullable=False),
        # DENORM de office.branch_id (copiado al agendar).
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branch.id"), nullable=False),
        sa.Column("product_id", sa.String(length=36), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column(
            "status_id",
            sa.String(length=36),
            sa.ForeignKey("appointment_status.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        # self-FK: la cadena de reagendamiento (la nueva apunta a la vieja).
        sa.Column(
            "previous_appointment_id",
            sa.String(length=36),
            sa.ForeignKey("appointment.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "ix_appointment_doctor_scheduled", "appointment", ["doctor_id", "scheduled_for"]
    )
    op.create_index(
        "ix_appointment_office_scheduled", "appointment", ["office_id", "scheduled_for"]
    )
    op.create_index(
        "ix_appointment_person_scheduled", "appointment", ["person_id", "scheduled_for"]
    )
    op.create_index(
        "ix_appointment_branch_scheduled_status",
        "appointment",
        ["branch_id", "scheduled_for", "status_id"],
    )

    # ── History de estado (PK·A·T, SIN deleted_at — append-only inmutable). ──
    op.create_table(
        "appointment_status_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "appointment_id",
            sa.String(length=36),
            sa.ForeignKey("appointment.id"),
            nullable=False,
        ),
        sa.Column(
            "from_status_id",
            sa.String(length=36),
            sa.ForeignKey("appointment_status.id"),
            nullable=True,
        ),
        sa.Column(
            "to_status_id",
            sa.String(length=36),
            sa.ForeignKey("appointment_status.id"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "ix_appointment_status_history_appointment_id",
        "appointment_status_history",
        ["appointment_id"],
    )

    # ── Change log de columnas no-estado (PK·A·T, SIN deleted_at). ──
    op.create_table(
        "appointment_change_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "appointment_id",
            sa.String(length=36),
            sa.ForeignKey("appointment.id"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(length=60), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "ix_appointment_change_log_appointment_id",
        "appointment_change_log",
        ["appointment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointment_change_log_appointment_id", table_name="appointment_change_log")
    op.drop_table("appointment_change_log")
    op.drop_index(
        "ix_appointment_status_history_appointment_id",
        table_name="appointment_status_history",
    )
    op.drop_table("appointment_status_history")
    op.drop_index("ix_appointment_branch_scheduled_status", table_name="appointment")
    op.drop_index("ix_appointment_person_scheduled", table_name="appointment")
    op.drop_index("ix_appointment_office_scheduled", table_name="appointment")
    op.drop_index("ix_appointment_doctor_scheduled", table_name="appointment")
    op.drop_table("appointment")
