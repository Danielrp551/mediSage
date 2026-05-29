"""add clinic office_operating_hours table

Revision ID: 0007_clinic_office_operating_hours
Revises: 0006_clinic_office
Create Date: 2026-05-29 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_clinic_office_operating_hours"
down_revision: str | None = "0006_clinic_office"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office_operating_hours",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # No ON DELETE CASCADE: the FK is RESTRICT (default). Hours are a value
        # aggregate of the office; a deleted office's hours stay soft-deletable
        # and are filtered out of any scheduling read by the office's deleted_at.
        sa.Column(
            "office_id",
            sa.String(length=36),
            sa.ForeignKey("office.id"),
            nullable=False,
        ),
        # 0=Mon .. 6=Sun (Python datetime.weekday()).
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(timezone=False), nullable=False),
        sa.Column("closes_at", sa.Time(timezone=False), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.CheckConstraint("closes_at > opens_at", name="ck_office_hours_closes_after_opens"),
        sa.CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_office_hours_day_of_week_range",
        ),
    )
    # NO unique on (office_id, day_of_week): multiple blocks per day are allowed.
    op.create_index("ix_office_operating_hours_office_id", "office_operating_hours", ["office_id"])


def downgrade() -> None:
    op.drop_index("ix_office_operating_hours_office_id", table_name="office_operating_hours")
    op.drop_table("office_operating_hours")
