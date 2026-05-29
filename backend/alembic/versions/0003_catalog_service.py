"""add catalog service table

Revision ID: 0003_catalog_service
Revises: 0002_catalog_vertical
Create Date: 2026-05-28 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_catalog_service"
down_revision: str | None = "0002_catalog_vertical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # No ON DELETE CASCADE: the FK is RESTRICT (default), reinforcing the
        # service-layer rule "a vertical with active services can't be deleted".
        sa.Column(
            "vertical_id",
            sa.String(length=36),
            sa.ForeignKey("vertical.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.UniqueConstraint("vertical_id", "code", name="uq_service_vertical_code"),
    )
    op.create_index("ix_service_vertical_id", "service", ["vertical_id"])


def downgrade() -> None:
    op.drop_index("ix_service_vertical_id", table_name="service")
    op.drop_table("service")
