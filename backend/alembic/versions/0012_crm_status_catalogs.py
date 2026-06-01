"""add crm lead/customer status catalogs + transition matrices

Revision ID: 0012_crm_status_catalogs
Revises: 0011_crm_person
Create Date: 2026-06-01 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_crm_status_catalogs"
down_revision: str | None = "0011_crm_person"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Catálogos configurables (PK·A·SD·T) ──────────────────────────
    op.create_table(
        "lead_status",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_initial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_won", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )

    op.create_table(
        "customer_status",  # idéntico a lead_status MENOS is_won
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_initial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )

    # ── Matrices de transición (ADR-008). PK·A·T, SIN deleted_at (config). ──
    op.create_table(
        "lead_status_transition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "from_lead_status_id",
            sa.String(length=36),
            sa.ForeignKey("lead_status.id"),
            nullable=False,
        ),
        sa.Column(
            "to_lead_status_id",
            sa.String(length=36),
            sa.ForeignKey("lead_status.id"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.UniqueConstraint(
            "from_lead_status_id",
            "to_lead_status_id",
            name="uq_lead_status_transition_from_to",
        ),
    )
    op.create_index(
        "ix_lead_status_transition_from_lead_status_id",
        "lead_status_transition",
        ["from_lead_status_id"],
    )

    op.create_table(
        "customer_status_transition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "from_customer_status_id",
            sa.String(length=36),
            sa.ForeignKey("customer_status.id"),
            nullable=False,
        ),
        sa.Column(
            "to_customer_status_id",
            sa.String(length=36),
            sa.ForeignKey("customer_status.id"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.UniqueConstraint(
            "from_customer_status_id",
            "to_customer_status_id",
            name="uq_customer_status_transition_from_to",
        ),
    )
    op.create_index(
        "ix_customer_status_transition_from_customer_status_id",
        "customer_status_transition",
        ["from_customer_status_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_status_transition_from_customer_status_id",
        table_name="customer_status_transition",
    )
    op.drop_table("customer_status_transition")
    op.drop_index(
        "ix_lead_status_transition_from_lead_status_id",
        table_name="lead_status_transition",
    )
    op.drop_table("lead_status_transition")
    op.drop_table("customer_status")
    op.drop_table("lead_status")
