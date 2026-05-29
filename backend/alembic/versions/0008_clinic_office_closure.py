"""add clinic office_closure table

Revision ID: 0008_clinic_office_closure
Revises: 0007_clinic_office_hours
Create Date: 2026-05-29 00:00:00

Revision id kept <= 32 chars (alembic_version.version_num is VARCHAR(32)):
"0008_clinic_office_closure" is 26.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_clinic_office_closure"
down_revision: str | None = "0007_clinic_office_hours"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office_closure",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # No ON DELETE CASCADE: the FK is RESTRICT (default). Closures are a value
        # aggregate of the office; a deleted office's closures stay soft-deletable
        # and are filtered out of any scheduling read by the office's deleted_at.
        sa.Column(
            "office_id",
            sa.String(length=36),
            sa.ForeignKey("office.id"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_office_closure_ends_after_starts"),
    )
    op.create_index("ix_office_closure_office_id", "office_closure", ["office_id"])


def downgrade() -> None:
    op.drop_index("ix_office_closure_office_id", table_name="office_closure")
    op.drop_table("office_closure")
