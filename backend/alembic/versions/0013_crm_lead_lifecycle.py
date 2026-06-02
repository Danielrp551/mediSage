"""add crm lead lifecycle: person_lead_status + history + assignment + activity

Revision ID: 0013_crm_lead_lifecycle
Revises: 0012_crm_status_catalogs
Create Date: 2026-06-02 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_crm_lead_lifecycle"
down_revision: str | None = "0012_crm_status_catalogs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── person_lead_status (PK·A·SD·T) — UNIQUE PARCIAL person_id ────────
    op.create_table(
        "person_lead_status",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "lead_status_id",
            sa.String(length=36),
            sa.ForeignKey("lead_status.id"),
            nullable=False,
        ),
        # FK forward (ADR-009): varchar(36)+index, SIN REFERENCES.
        sa.Column("source_campaign_id", sa.String(length=36), nullable=True),
        sa.Column("entered_status_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_person_lead_status_person",
        "person_lead_status",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_person_lead_status_campaign", "person_lead_status", ["source_campaign_id"])

    # ── lead_status_history (PK·A·T, SIN deleted_at — audit inmutable) ───
    op.create_table(
        "lead_status_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "from_lead_status_id",
            sa.String(length=36),
            sa.ForeignKey("lead_status.id"),
            nullable=True,
        ),
        sa.Column(
            "to_lead_status_id",
            sa.String(length=36),
            sa.ForeignKey("lead_status.id"),
            nullable=False,
        ),
        sa.Column("source_campaign_id", sa.String(length=36), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_lead_status_history_person_id", "lead_status_history", ["person_id"])
    op.create_index(
        "ix_lead_status_history_source_campaign_id",
        "lead_status_history",
        ["source_campaign_id"],
    )

    # ── lead_assignment (PK·A·SD·T) — UNIQUE PARCIAL person_id ───────────
    op.create_table(
        "lead_assignment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "advisor_user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), nullable=True),  # FK lógica (NULL=auto)
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_lead_assignment_person",
        "lead_assignment",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_lead_assignment_advisor", "lead_assignment", ["advisor_user_id"])

    # ── lead_activity (PK·A·T, SIN deleted_at; "borrar" = active=false) ──
    op.create_table(
        "lead_activity",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "advisor_user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id"),
            nullable=True,  # NULL/SYSTEM en eventos de sistema
        ),
        sa.Column("activity_type", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        # FKs forward (ADR-009): varchar(36)+index, SIN REFERENCES.
        sa.Column("related_appointment_id", sa.String(length=36), nullable=True),
        sa.Column("related_conversation_id", sa.String(length=36), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_lead_activity_person_id", "lead_activity", ["person_id"])
    op.create_index(
        "ix_lead_activity_related_appointment_id", "lead_activity", ["related_appointment_id"]
    )
    op.create_index(
        "ix_lead_activity_related_conversation_id", "lead_activity", ["related_conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_lead_activity_related_conversation_id", table_name="lead_activity")
    op.drop_index("ix_lead_activity_related_appointment_id", table_name="lead_activity")
    op.drop_index("ix_lead_activity_person_id", table_name="lead_activity")
    op.drop_table("lead_activity")
    op.drop_index("ix_lead_assignment_advisor", table_name="lead_assignment")
    op.drop_index("uq_lead_assignment_person", table_name="lead_assignment")
    op.drop_table("lead_assignment")
    op.drop_index("ix_lead_status_history_source_campaign_id", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_person_id", table_name="lead_status_history")
    op.drop_table("lead_status_history")
    op.drop_index("ix_person_lead_status_campaign", table_name="person_lead_status")
    op.drop_index("uq_person_lead_status_person", table_name="person_lead_status")
    op.drop_table("person_lead_status")
