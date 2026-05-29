"""add catalog product table

Revision ID: 0004_catalog_product
Revises: 0003_catalog_service
Create Date: 2026-05-28 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_catalog_product"
down_revision: str | None = "0003_catalog_service"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # FKs are RESTRICT (default): the service-layer guards block deleting a
        # parent that still has active children before the DB constraint fires.
        sa.Column(
            "service_id",
            sa.String(length=36),
            sa.ForeignKey("service.id"),
            nullable=False,
        ),
        # Denormalized parent vertical, copied from the service on create.
        sa.Column(
            "vertical_id",
            sa.String(length=36),
            sa.ForeignKey("vertical.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("base_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'PEN'")),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        sa.Column(
            "requires_appointment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("is_package", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("min_hours_to_cancel", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.UniqueConstraint("service_id", "code", name="uq_product_service_code"),
    )
    op.create_index("ix_product_service_id", "product", ["service_id"])
    op.create_index("ix_product_vertical_id", "product", ["vertical_id"])


def downgrade() -> None:
    op.drop_index("ix_product_vertical_id", table_name="product")
    op.drop_index("ix_product_service_id", table_name="product")
    op.drop_table("product")
