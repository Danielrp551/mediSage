"""add clinic office table + office_vertical M:N

Revision ID: 0006_clinic_office
Revises: 0005_clinic_branch
Create Date: 2026-05-29 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_clinic_office"
down_revision: str | None = "0005_clinic_branch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # No ON DELETE CASCADE: the FK is RESTRICT (default), reinforcing the
        # service-layer rule "a branch with active offices can't be deleted".
        sa.Column(
            "branch_id",
            sa.String(length=36),
            sa.ForeignKey("branch.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("room_number", sa.String(length=20), nullable=True),
        sa.Column("floor", sa.String(length=20), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.UniqueConstraint("branch_id", "code", name="uq_office_branch_code"),
    )
    op.create_index("ix_office_branch_id", "office", ["branch_id"])

    # M:N office ↔ catalog.vertical. office_id CASCADE (deleting an office may
    # clean its associations); vertical_id RESTRICT (backstop against a
    # hard-delete of a vertical still attached to offices — the normal
    # soft-delete path leaves the rows and is filtered out at query time).
    op.create_table(
        "office_vertical",
        sa.Column(
            "office_id",
            sa.String(length=36),
            sa.ForeignKey("office.id", ondelete="CASCADE"),
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
    op.drop_table("office_vertical")
    op.drop_index("ix_office_branch_id", table_name="office")
    op.drop_table("office")
