"""add marketing promotion + M:N campaign_promotion / promotion_product

Revision ID: 0023_marketing_promotion
Revises: 0022_marketing_campaign
Create Date: 2026-06-09 00:00:00

Crea `promotion` (PK·A·SD·T, discount discriminado) y las 2 tablas M:N (PK compuesta,
FK CASCADE): `campaign_promotion` (campaign ↔ promotion) y `promotion_product`
(promotion ↔ catalog.product). Tablas nuevas y vacías → sin riesgo de FK huérfana
(a diferencia de 0022, que cerraba FKs sobre columnas pre-existentes).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_marketing_promotion"
down_revision: str | None = "0022_marketing_campaign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Promotion (PK·A·SD·T) — discount discriminado por discount_type. ──
    op.create_table(
        "promotion",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'PEN'")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("max_uses_total", sa.Integer(), nullable=True),
        sa.Column("max_uses_per_person", sa.Integer(), nullable=True),
        sa.Column(
            "applies_to_all_products",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_promotion_code", "promotion", ["code"], unique=True)

    # ── M:N campaign ↔ promotion (PK compuesta, FK CASCADE). ──
    op.create_table(
        "campaign_promotion",
        sa.Column(
            "campaign_id",
            sa.String(length=36),
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "promotion_id",
            sa.String(length=36),
            sa.ForeignKey("promotion.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ── M:N promotion ↔ catalog.product (PK compuesta, FK CASCADE). ──
    op.create_table(
        "promotion_product",
        sa.Column(
            "promotion_id",
            sa.String(length=36),
            sa.ForeignKey("promotion.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            sa.String(length=36),
            sa.ForeignKey("product.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("promotion_product")
    op.drop_table("campaign_promotion")
    op.drop_index("uq_promotion_code", table_name="promotion")
    op.drop_table("promotion")
