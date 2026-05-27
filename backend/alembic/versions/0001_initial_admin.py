"""initial admin tables

Revision ID: 0001_initial_admin
Revises:
Create Date: 2026-05-26 00:00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_admin"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permission",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("module", sa.String(length=60), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_permission_code", "permission", ["code"], unique=True)
    op.create_index("ix_permission_module", "permission", ["module"])

    op.create_table(
        "role",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_role_name", "role", ["name"], unique=True)

    op.create_table(
        "user",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("second_last_name", sa.String(length=80), nullable=True),
        sa.Column("document_type", sa.String(length=20), nullable=True),
        sa.Column("document_number", sa.String(length=40), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_user_document_number", "user", ["document_number"])

    op.create_table(
        "user_role",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.String(length=36), sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.String(length=36), sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.String(length=36), sa.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "user_permission",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.String(length=36), sa.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "token_family",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("family_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_jti", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_token_family_family_id", "token_family", ["family_id"], unique=True)
    op.create_index("ix_token_family_user_id", "token_family", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_token_family_user_id", table_name="token_family")
    op.drop_index("ix_token_family_family_id", table_name="token_family")
    op.drop_table("token_family")
    op.drop_table("user_permission")
    op.drop_table("role_permission")
    op.drop_table("user_role")
    op.drop_index("ix_user_document_number", table_name="user")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")
    op.drop_index("ix_role_name", table_name="role")
    op.drop_table("role")
    op.drop_index("ix_permission_module", table_name="permission")
    op.drop_index("ix_permission_code", table_name="permission")
    op.drop_table("permission")
