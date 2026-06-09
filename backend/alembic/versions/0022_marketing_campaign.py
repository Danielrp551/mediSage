"""add marketing campaign + cierre de las 3 FK forward (ADR-009)

Revision ID: 0022_marketing_campaign
Revises: 0021_scheduling_appointment
Create Date: 2026-06-09 00:00:00

Crea la tabla `campaign` (PK·A·SD·T) con FK REAL a catalog.vertical, y CIERRA las 3 FK
forward que crm/conversations dejaron diferidas (ADR-009) ahora que `campaign` existe:
  - crm.person_lead_status.source_campaign_id  → campaign.id
  - crm.lead_status_history.source_campaign_id → campaign.id
  - conversations.channel_account.default_campaign_id → campaign.id
Los índices de esas 3 columnas YA existen (creados por 0013/0015) → NO se recrean,
solo se agrega la FK. Seguro hoy: todos los valores son NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_marketing_campaign"
down_revision: str | None = "0021_scheduling_appointment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Campaign (PK·A·SD·T) — FK REAL a catalog.vertical (NULL = transversal). ──
    op.create_table(
        "campaign",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column(
            "target_vertical_id",
            sa.String(length=36),
            sa.ForeignKey("vertical.id"),
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("uq_campaign_code", "campaign", ["code"], unique=True)
    op.create_index("ix_campaign_target_vertical", "campaign", ["target_vertical_id"])
    op.create_index("ix_campaign_status", "campaign", ["status"])

    # ── Cierre de las 3 FK forward (ADR-009). campaign YA existe. Los índices de estas
    #    columnas YA existen (0013/0015) → NO recrearlos, solo la FK. Hoy todo es NULL. ──
    op.create_foreign_key(
        "fk_person_lead_status_campaign",
        "person_lead_status",
        "campaign",
        ["source_campaign_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_lead_status_history_campaign",
        "lead_status_history",
        "campaign",
        ["source_campaign_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_channel_account_campaign",
        "channel_account",
        "campaign",
        ["default_campaign_id"],
        ["id"],
    )


def downgrade() -> None:
    # Dropear las 3 FK forward ANTES de drop_table campaign (los índices NO los creó
    # esta migración → no se dropean acá).
    op.drop_constraint("fk_channel_account_campaign", "channel_account", type_="foreignkey")
    op.drop_constraint("fk_lead_status_history_campaign", "lead_status_history", type_="foreignkey")
    op.drop_constraint("fk_person_lead_status_campaign", "person_lead_status", type_="foreignkey")
    op.drop_index("ix_campaign_status", table_name="campaign")
    op.drop_index("ix_campaign_target_vertical", table_name="campaign")
    op.drop_index("uq_campaign_code", table_name="campaign")
    op.drop_table("campaign")
