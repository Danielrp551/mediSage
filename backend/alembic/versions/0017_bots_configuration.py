"""add bots configuration: bot_configuration + bot_configuration_version + forward FK constraints

Revision ID: 0017_bots_configuration
Revises: 0016_conv_threads
Create Date: 2026-06-04 00:00:00

🔑 F1 del módulo bots. Crea `bot_configuration_version` (versionado inmutable del prompt/provider/
model/params) + `bot_configuration` (contenedor; current_version_id → versión vigente). La FK
`bot_configuration.current_version_id → bot_configuration_version.id` es CIRCULAR con
`bot_configuration_version.bot_configuration_id → bot_configuration.id`: se crean ambas tablas SIN
la FK inline y se agregan con `create_foreign_key` al final (Postgres resuelve el ciclo; en
sqlite/create_all el ForeignKey inline del modelo es tolerado porque ambas tablas se crean juntas).

Además cierra las DOS forward FK que `conversations` dejó como varchar(36) sin constraint (ADR-009):
`channel_account.bot_configuration_id` y `conversation.bot_configuration_id` → `bot_configuration.id`
(ALTER TABLE ADD CONSTRAINT, Postgres-only; seguras: hoy todos esos valores son NULL — bots no
existía). NO se agrega relationship ORM en conversations (mantiene su mapper intacto).

`is_active` de la versión = `ActiveMixin.active` (NO columna aparte; ver el modelo). JSONB en
`parameters`. El smoke (create_all sqlite) NO corre esta migración (JSONB + ALTER ADD CONSTRAINT son
Postgres-only) → se valida vía QA E2E sobre Postgres (patrón crm 0013 / conversations 0016).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_bots_configuration"
down_revision: str | None = "0016_conv_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── bot_configuration_version (PK·A·SD·T) — se crea ANTES (current_version_id la referencia) ─
    op.create_table(
        "bot_configuration_version",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # FK → bot_configuration se agrega abajo (circular).
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("external_webhook_url", sa.String(length=500), nullable=True),
        sa.Column("external_webhook_secret_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # `is_active` de la spec = ActiveMixin.active (NO una segunda columna).
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    # ── bot_configuration (PK·A·SD·T) ──
    op.create_table(
        "bot_configuration",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("bot_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("max_turns_per_conversation", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_bot_configuration_code",
        "bot_configuration",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_bot_config_version_number",
        "bot_configuration_version",
        ["bot_configuration_id", "version"],
        unique=True,
    )
    # nombre = el que autogenera el modelo con index=True (ix_<tabla>_<col>) → coincide con el
    # índice que create_all produce en el smoke sqlite (sin drift modelo↔migración).
    op.create_index(
        "ix_bot_configuration_version_bot_configuration_id",
        "bot_configuration_version",
        ["bot_configuration_id"],
    )
    op.create_index(
        "ix_bot_configuration_current_version_id",
        "bot_configuration",
        ["current_version_id"],
    )
    # ── FKs circulares (se agregan tras existir ambas tablas) ──
    op.create_foreign_key(
        "fk_bot_config_version_config",
        "bot_configuration_version",
        "bot_configuration",
        ["bot_configuration_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_bot_configuration_current_version",
        "bot_configuration",
        "bot_configuration_version",
        ["current_version_id"],
        ["id"],
    )
    # ── forward FK constraints ADITIVAS a conversations (ADR-009; Postgres-only) ──
    op.create_foreign_key(
        "fk_channel_account_bot_configuration",
        "channel_account",
        "bot_configuration",
        ["bot_configuration_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_conversation_bot_configuration",
        "conversation",
        "bot_configuration",
        ["bot_configuration_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_conversation_bot_configuration", "conversation", type_="foreignkey")
    op.drop_constraint(
        "fk_channel_account_bot_configuration", "channel_account", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_bot_configuration_current_version", "bot_configuration", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_bot_config_version_config", "bot_configuration_version", type_="foreignkey"
    )
    op.drop_index("ix_bot_configuration_current_version_id", table_name="bot_configuration")
    op.drop_index(
        "ix_bot_configuration_version_bot_configuration_id",
        table_name="bot_configuration_version",
    )
    op.drop_index("uq_bot_config_version_number", table_name="bot_configuration_version")
    op.drop_index("uq_bot_configuration_code", table_name="bot_configuration")
    op.drop_table("bot_configuration")
    op.drop_table("bot_configuration_version")
