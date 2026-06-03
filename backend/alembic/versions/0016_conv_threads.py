"""add conversations threads: conversation + message_outbox + assignment_log

Revision ID: 0016_conv_threads
Revises: 0015_conv_channel_account
Create Date: 2026-06-03 00:00:00

🔑 NO crea `message` ni `message_attachment` (el stream de mensajes vive en Firestore
como read-model, ADR-011/CQRS). Crea: `conversation` (control plane) + `message_outbox`
(cola transaccional Postgres→Firestore) + `conversation_assignment_log` (audit handoff)
+ la FK aditiva `lead_activity.related_conversation_id → conversation.id` (ADR-009). La
idempotencia que antes daba el UNIQUE parcial de `message` ahora la da el PK UNIQUE de
`message_outbox.id` (= mid) + el doc-id en Firestore.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_conv_threads"
down_revision: str | None = "0015_conv_channel_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── conversation (PK·A·SD·T) — UNIQUE PARCIAL 1-open ─────────────────
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "channel_account_id",
            sa.String(length=36),
            sa.ForeignKey("channel_account.id"),
            nullable=False,
        ),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_type", sa.String(length=20), nullable=False),
        sa.Column(
            "assignee_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True
        ),
        # forward FK (ADR-009): varchar(36)+index, SIN REFERENCES.
        sa.Column("bot_configuration_id", sa.String(length=36), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=255), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_conversation_channel_account_id", "conversation", ["channel_account_id"])
    op.create_index("ix_conversation_person_id", "conversation", ["person_id"])
    op.create_index("ix_conversation_assignee_user_id", "conversation", ["assignee_user_id"])
    op.create_index(
        "ix_conversation_bot_configuration_id", "conversation", ["bot_configuration_id"]
    )
    # UNIQUE PARCIAL 1-open (Postgres-only; el modelo lleva sqlite_where para el smoke).
    op.create_index(
        "uq_conversation_person_channel_open",
        "conversation",
        ["person_id", "channel_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND deleted_at IS NULL"),
    )

    # ── message_outbox (A·T, SIN deleted_at — cola transaccional Postgres→Firestore) ─
    # id = el `mid` (wamid inbound / uuid outbound) → varchar(255) (el wamid de Meta es
    # más largo que un uuid). PK UNIQUE = idempotencia (ON CONFLICT (id) DO NOTHING).
    op.create_table(
        "message_outbox",
        sa.Column("id", sa.String(length=255), primary_key=True),  # = mid (wamid/uuid)
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column(
            "op", sa.String(length=40), nullable=False
        ),  # message_create|message_status|conversation_upsert
        sa.Column("payload", postgresql.JSONB(), nullable=False),  # el doc a escribir en Firestore
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("processed_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_message_outbox_conversation_id", "message_outbox", ["conversation_id"])
    op.create_index("ix_message_outbox_status_created", "message_outbox", ["status", "created_on"])

    # ── conversation_assignment_log (A·T, SIN deleted_at — audit inmutable) ──
    op.create_table(
        "conversation_assignment_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column("from_assignee_type", sa.String(length=20), nullable=True),
        sa.Column(
            "from_assignee_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True
        ),
        sa.Column("to_assignee_type", sa.String(length=20), nullable=False),
        sa.Column(
            "to_assignee_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "by_actor_user_id", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "ix_conversation_assignment_log_conversation_id",
        "conversation_assignment_log",
        ["conversation_id"],
    )

    # ── FK ADITIVA crm (ADR-009): lead_activity.related_conversation_id → conversation.id ─
    # Seguro: todos los valores actuales de la columna son NULL. Postgres-only (no corre en
    # sqlite/create_all; el smoke valida con la columna como String(36) plano).
    op.create_foreign_key(
        "fk_lead_activity_conversation",
        "lead_activity",
        "conversation",
        ["related_conversation_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_lead_activity_conversation", "lead_activity", type_="foreignkey")
    op.drop_index(
        "ix_conversation_assignment_log_conversation_id",
        table_name="conversation_assignment_log",
    )
    op.drop_table("conversation_assignment_log")
    op.drop_index("ix_message_outbox_status_created", table_name="message_outbox")
    op.drop_index("ix_message_outbox_conversation_id", table_name="message_outbox")
    op.drop_table("message_outbox")
    op.drop_index("uq_conversation_person_channel_open", table_name="conversation")
    op.drop_index("ix_conversation_bot_configuration_id", table_name="conversation")
    op.drop_index("ix_conversation_assignee_user_id", table_name="conversation")
    op.drop_index("ix_conversation_person_id", table_name="conversation")
    op.drop_index("ix_conversation_channel_account_id", table_name="conversation")
    op.drop_table("conversation")
