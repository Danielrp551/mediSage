"""add bots engine state: conversation_bot_state + bot_event + bot_tool_call

Revision ID: 0019_bots_engine_state
Revises: 0018_bots_tools
Create Date: 2026-06-05 00:00:00

🔑 F3 del módulo bots (data plane del motor). Crea `conversation_bot_state` (estado del bot por
hilo; UNIQUE conversation_id) + `bot_event` (traza inmutable por turno; índice NO único conv+turn —
varios eventos por turno; SIN deleted_at) + `bot_tool_call` (traza por invocación de tool; SIN deleted_at). `bot_event.metadata`
es JSONB (atributo Python `event_metadata`). `input/output_message_id` son varchar(255) PLANOS = el
`mid` (doc-id Firestore), NO FK (no hay tabla message; ADR-011). JSONB en collected_slots/arguments/
result/metadata. El smoke (create_all sqlite) NO corre esta migración (JSONB es Postgres-only) → se
valida vía QA E2E sobre Postgres (patrón crm 0013 / conversations 0016 / bots 0017-0018).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_bots_engine_state"
down_revision: str | None = "0018_bots_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── conversation_bot_state (PK·A·SD·T; UNIQUE conversation_id) ──────
    op.create_table(
        "conversation_bot_state",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column(
            "bot_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("bot_configuration.id"),
            nullable=False,
        ),
        sa.Column(
            "bot_configuration_version_id",
            sa.String(length=36),
            sa.ForeignKey("bot_configuration_version.id"),
            nullable=False,
        ),
        sa.Column("current_intent", sa.String(length=80), nullable=True),
        sa.Column("collected_slots", postgresql.JSONB(), nullable=False),
        sa.Column("last_node", sa.String(length=120), nullable=True),
        sa.Column("last_bot_turn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "uq_conversation_bot_state_conversation",
        "conversation_bot_state",
        ["conversation_id"],
        unique=True,
    )
    op.create_index(
        "ix_conversation_bot_state_config",
        "conversation_bot_state",
        ["bot_configuration_id"],
    )
    op.create_index(
        "ix_conversation_bot_state_version",
        "conversation_bot_state",
        ["bot_configuration_version_id"],
    )
    # ── bot_event (PK·A·T, SIN deleted_at — traza) ─────────────────────
    op.create_table(
        "bot_event",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column(
            "bot_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("bot_configuration.id"),
            nullable=False,
        ),
        sa.Column(
            "bot_configuration_version_id",
            sa.String(length=36),
            sa.ForeignKey("bot_configuration_version.id"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("input_message_id", sa.String(length=255), nullable=True),  # mid Firestore, NO FK
        sa.Column(
            "output_message_id", sa.String(length=255), nullable=True
        ),  # mid Firestore, NO FK
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_estimated_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_bot_event_conversation_id", "bot_event", ["conversation_id"])
    # NO único: varios eventos por turno (turn_started + turn_completed/failed) comparten turn_number.
    op.create_index(
        "ix_bot_event_conversation_turn",
        "bot_event",
        ["conversation_id", "turn_number"],
    )
    op.create_index(
        "ix_bot_event_config_created", "bot_event", ["bot_configuration_id", "created_on"]
    )
    op.create_index("ix_bot_event_type_created", "bot_event", ["event_type", "created_on"])
    # ── bot_tool_call (PK·A·T, SIN deleted_at — traza) ─────────────────
    op.create_table(
        "bot_tool_call",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column(
            "bot_event_id", sa.String(length=36), sa.ForeignKey("bot_event.id"), nullable=True
        ),
        sa.Column(
            "bot_tool_id", sa.String(length=36), sa.ForeignKey("bot_tool.id"), nullable=False
        ),
        sa.Column("tool_use_id", sa.String(length=255), nullable=True),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_bot_tool_call_conversation_id", "bot_tool_call", ["conversation_id"])
    op.create_index("ix_bot_tool_call_event_id", "bot_tool_call", ["bot_event_id"])
    op.create_index("ix_bot_tool_call_tool_id", "bot_tool_call", ["bot_tool_id"])


def downgrade() -> None:
    op.drop_table("bot_tool_call")
    op.drop_index("ix_bot_event_type_created", table_name="bot_event")
    op.drop_index("ix_bot_event_config_created", table_name="bot_event")
    op.drop_index("ix_bot_event_conversation_turn", table_name="bot_event")
    op.drop_index("ix_bot_event_conversation_id", table_name="bot_event")
    op.drop_table("bot_event")
    op.drop_index("ix_conversation_bot_state_version", table_name="conversation_bot_state")
    op.drop_index("ix_conversation_bot_state_config", table_name="conversation_bot_state")
    op.drop_index("uq_conversation_bot_state_conversation", table_name="conversation_bot_state")
    op.drop_table("conversation_bot_state")
