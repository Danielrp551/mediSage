"""add marketing promotion_usage (audit inmutable de redenciones)

Revision ID: 0024_marketing_promotion_usage
Revises: 0023_marketing_promotion
Create Date: 2026-06-09 00:00:00

Crea `promotion_usage` (PK·A·T, SIN deleted_at — audit append-only inmutable). FKs reales
a promotion/person/product (NOT NULL) + appointment/campaign (nullables). Snapshotea
original/discount/final + currency. 6 índices simples + 1 UNIQUE PARCIAL no-stacking
(`appointment_id WHERE appointment_id IS NOT NULL`) — una promo por cita; el backstop de
carrera del chequeo proactivo del service. Tabla NUEVA y vacía → sin riesgo de FK huérfana.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_marketing_promotion_usage"
down_revision: str | None = "0023_marketing_promotion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── PromotionUsage (PK·A·T, SIN deleted_at) — audit inmutable de redenciones. ──
    op.create_table(
        "promotion_usage",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "promotion_id",
            sa.String(length=36),
            sa.ForeignKey("promotion.id"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(length=36),
            sa.ForeignKey("product.id"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            sa.String(length=36),
            sa.ForeignKey("appointment.id"),
            nullable=True,
        ),
        sa.Column(
            "campaign_id",
            sa.String(length=36),
            sa.ForeignKey("campaign.id"),
            nullable=True,
        ),
        sa.Column("original_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("final_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_promotion_usage_promotion", "promotion_usage", ["promotion_id"])
    op.create_index("ix_promotion_usage_person", "promotion_usage", ["person_id"])
    op.create_index("ix_promotion_usage_product", "promotion_usage", ["product_id"])
    op.create_index("ix_promotion_usage_appointment", "promotion_usage", ["appointment_id"])
    op.create_index("ix_promotion_usage_campaign", "promotion_usage", ["campaign_id"])
    op.create_index("ix_promotion_usage_created_on", "promotion_usage", ["created_on"])
    # NO stacking: UNIQUE PARCIAL (una promo por cita). SIN cláusula deleted_at (no hay
    # SoftDelete). postgresql_where para prod; el smoke usa el modelo ORM (sqlite_where).
    op.create_index(
        "uq_promotion_usage_appointment",
        "promotion_usage",
        ["appointment_id"],
        unique=True,
        postgresql_where=sa.text("appointment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_promotion_usage_appointment", table_name="promotion_usage")
    op.drop_index("ix_promotion_usage_created_on", table_name="promotion_usage")
    op.drop_index("ix_promotion_usage_campaign", table_name="promotion_usage")
    op.drop_index("ix_promotion_usage_appointment", table_name="promotion_usage")
    op.drop_index("ix_promotion_usage_product", table_name="promotion_usage")
    op.drop_index("ix_promotion_usage_person", table_name="promotion_usage")
    op.drop_index("ix_promotion_usage_promotion", table_name="promotion_usage")
    op.drop_table("promotion_usage")
