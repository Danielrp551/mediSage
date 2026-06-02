"""add crm customer lifecycle: person_customer_status + customer_status_history

Revision ID: 0014_crm_customer_lifecycle
Revises: 0013_crm_lead_lifecycle
Create Date: 2026-06-02 12:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_crm_customer_lifecycle"
down_revision: str | None = "0013_crm_lead_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── person_customer_status (PK·A·SD·T) — UNIQUE PARCIAL person_id ─────
    op.create_table(
        "person_customer_status",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "customer_status_id",
            sa.String(length=36),
            sa.ForeignKey("customer_status.id"),
            nullable=False,
        ),
        sa.Column("became_customer_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entered_status_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_person_customer_status_person",
        "person_customer_status",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── customer_status_history (PK·A·T, SIN deleted_at — audit inmutable) ─
    op.create_table(
        "customer_status_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "from_customer_status_id",
            sa.String(length=36),
            sa.ForeignKey("customer_status.id"),
            nullable=True,
        ),
        sa.Column(
            "to_customer_status_id",
            sa.String(length=36),
            sa.ForeignKey("customer_status.id"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_customer_status_history_person", "customer_status_history", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_status_history_person", table_name="customer_status_history")
    op.drop_table("customer_status_history")
    op.drop_index("uq_person_customer_status_person", table_name="person_customer_status")
    op.drop_table("person_customer_status")
