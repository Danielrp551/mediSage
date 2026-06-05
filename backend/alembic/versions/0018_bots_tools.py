"""add bots tools: bot_tool + M:N bot_configuration_tool

Revision ID: 0018_bots_tools
Revises: 0017_bots_configuration
Create Date: 2026-06-04 00:00:00

🔑 F2 del módulo bots. Crea `bot_tool` (catálogo configurable de herramientas invocables por el
LLM; `code` UNIQUE parcial vivo) + el M:N `bot_configuration_tool` (qué tools ve cada bot; PK
compuesta, ondelete CASCADE). JSONB en `parameters_schema`. El UNIQUE parcial usa
`postgresql_where=deleted_at IS NULL` (en el modelo, el `sqlite_where` lo espeja para create_all).
El smoke (create_all sqlite) NO corre esta migración (JSONB es Postgres-only) → se valida vía QA
E2E sobre Postgres (patrón crm 0013 / conversations 0016 / bots 0017).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_bots_tools"
down_revision: str | None = "0017_bots_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── bot_tool (PK·A·SD·T) ──────────────────────────────────────────
    op.create_table(
        "bot_tool",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parameters_schema", postgresql.JSONB(), nullable=False),
        sa.Column("target_service", sa.String(length=120), nullable=False),
        sa.Column(
            "requires_confirmation",
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
    op.create_index(
        "uq_bot_tool_code",
        "bot_tool",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # ── M:N bot_configuration_tool (PK compuesta, ondelete CASCADE) ────
    op.create_table(
        "bot_configuration_tool",
        sa.Column(
            "bot_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("bot_configuration.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "bot_tool_id",
            sa.String(length=36),
            sa.ForeignKey("bot_tool.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("bot_configuration_tool")
    op.drop_index("uq_bot_tool_code", table_name="bot_tool")
    op.drop_table("bot_tool")
