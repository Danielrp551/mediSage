"""add calendar connection + source (integración de calendario externo, Fase 1)

Revision ID: 0025_calendar_connection
Revises: 0024_marketing_promotion_usage
Create Date: 2026-06-22 00:00:00

Crea `calendar_connection` (PK·A·SD·T — cuenta OAuth de la clínica; tokens en Secret
Manager, NO acá) + `calendar_source` (PK·A·SD·T — calendario→sede). 2 UNIQUE PARCIALES
(provider+email / connection+external_calendar, WHERE deleted_at IS NULL). FK real
calendar_source.branch_id → branch (RESTRICT, nullable) + FK connection_id → calendar_
connection (CASCADE). Tablas NUEVAS vacías → sin riesgo de FK huérfana (a diferencia de
la lección §20 de marketing, que agregaba un FK a una columna pre-existente).

En la migración el UNIQUE PARCIAL usa solo `postgresql_where` (NO sqlite_where — eso vive
solo en el Index del modelo ORM, para que el smoke en sqlite reproduzca el índice).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_calendar_connection"
down_revision: str | None = "0024_marketing_promotion_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── CalendarConnection (PK·A·SD·T) ──
    op.create_table(
        "calendar_connection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("account_email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("secret_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="connected"
        ),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_calendar_connection_provider_email",
        "calendar_connection",
        ["provider", "account_email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── CalendarSource (PK·A·SD·T) ──
    op.create_table(
        "calendar_source",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("calendar_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("external_calendar_name", sa.String(length=255), nullable=False),
        sa.Column(
            "branch_id",
            sa.String(length=36),
            sa.ForeignKey("branch.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_calendar_source_connection", "calendar_source", ["connection_id"])
    op.create_index("ix_calendar_source_branch", "calendar_source", ["branch_id"])
    op.create_index(
        "uq_calendar_source_connection_external",
        "calendar_source",
        ["connection_id", "external_calendar_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_calendar_source_connection_external", table_name="calendar_source")
    op.drop_index("ix_calendar_source_branch", table_name="calendar_source")
    op.drop_index("ix_calendar_source_connection", table_name="calendar_source")
    op.drop_table("calendar_source")
    op.drop_index(
        "uq_calendar_connection_provider_email", table_name="calendar_connection"
    )
    op.drop_table("calendar_connection")
