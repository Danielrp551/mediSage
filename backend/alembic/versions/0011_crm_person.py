"""add crm person + person_contact_identifier tables

Revision ID: 0011_crm_person
Revises: 0010_staff_doctor_availability
Create Date: 2026-06-01 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_crm_person"
down_revision: str | None = "0010_staff_doctor_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("second_last_name", sa.String(length=80), nullable=True),
        sa.Column("document_type", sa.String(length=20), nullable=True),
        sa.Column("document_number", sa.String(length=40), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_person_document_number", "person", ["document_number"])

    op.create_table(
        "person_contact_identifier",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # person_id RESTRICT (default): el soft-delete de la persona deja las filas
        # y se filtran por su deleted_at; el hard-delete queda bloqueado de backstop.
        sa.Column(
            "person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id"),
            nullable=False,
        ),
        sa.Column("channel_type", sa.String(length=40), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_index(
        "ix_person_contact_identifier_person_id",
        "person_contact_identifier",
        ["person_id"],
    )
    # Partial UNIQUE: a LIVE (channel_type, identifier) is unique; freed after
    # soft-delete (postgresql_where). El service respalda con un chequeo proactivo
    # (409 IDENTIFIER_TAKEN).
    op.create_index(
        "uq_contact_identifier_channel_value",
        "person_contact_identifier",
        ["channel_type", "identifier"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_contact_identifier_channel_value", table_name="person_contact_identifier")
    op.drop_index("ix_person_contact_identifier_person_id", table_name="person_contact_identifier")
    op.drop_table("person_contact_identifier")
    op.drop_index("ix_person_document_number", table_name="person")
    op.drop_table("person")
