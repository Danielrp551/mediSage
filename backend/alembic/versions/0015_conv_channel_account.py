"""add conversations channel_account table

Revision ID: 0015_conv_channel_account
Revises: 0014_crm_customer_lifecycle
Create Date: 2026-06-03 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_conv_channel_account"
down_revision: str | None = "0014_crm_customer_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_account",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("external_identifier", sa.String(length=255), nullable=False),
        sa.Column("secret_name", sa.String(length=255), nullable=True),
        sa.Column("webhook_verify_token", sa.String(length=255), nullable=True),
        sa.Column("phone_number_id", sa.String(length=64), nullable=True),
        # FKs forward (ADR-009): varchar(36) + index, SIN constraint (las tablas
        # bot_configuration / campaign aún no existen). Hoy siempre NULL.
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=True),
        sa.Column("default_campaign_id", sa.String(length=36), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    # Partial UNIQUE: a LIVE (channel_type, external_identifier) is globally unique;
    # freed after soft-delete (postgresql_where). Postgres-only (la migración no corre
    # en sqlite; el modelo lleva sqlite_where para reproducirlo en el smoke create_all).
    op.create_index(
        "uq_channel_account_type_external",
        "channel_account",
        ["channel_type", "external_identifier"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_channel_account_bot_configuration_id",
        "channel_account",
        ["bot_configuration_id"],
    )
    op.create_index(
        "ix_channel_account_default_campaign_id",
        "channel_account",
        ["default_campaign_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_account_default_campaign_id", table_name="channel_account")
    op.drop_index("ix_channel_account_bot_configuration_id", table_name="channel_account")
    op.drop_index("uq_channel_account_type_external", table_name="channel_account")
    op.drop_table("channel_account")
