"""add scheduling appointment_status catalog + transition matrix

Revision ID: 0020_scheduling_status
Revises: 0019_bots_engine_state
Create Date: 2026-06-07 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_scheduling_status"
down_revision: str | None = "0019_bots_engine_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Catálogo configurable de estados de cita (PK·A·SD·T) ──────────
    op.create_table(
        "appointment_status",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_initial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_active_attention",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )

    # ── Matriz de transiciones (ADR-008). PK·A·T, SIN deleted_at (config). ──
    op.create_table(
        "appointment_status_transition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "from_status_id",
            sa.String(length=36),
            sa.ForeignKey("appointment_status.id"),
            nullable=False,
        ),
        sa.Column(
            "to_status_id",
            sa.String(length=36),
            sa.ForeignKey("appointment_status.id"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.UniqueConstraint(
            "from_status_id",
            "to_status_id",
            name="uq_appointment_status_transition_from_to",
        ),
    )
    op.create_index(
        "ix_appointment_status_transition_from_status_id",
        "appointment_status_transition",
        ["from_status_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_appointment_status_transition_from_status_id",
        table_name="appointment_status_transition",
    )
    op.drop_table("appointment_status_transition")
    op.drop_table("appointment_status")
