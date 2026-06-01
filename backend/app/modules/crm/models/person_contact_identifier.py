"""
A contact handle for a Person on a given channel (phone E.164, email, chat_id…).
The dedup rule (ADR-003) is a PARTIAL unique index on (channel_type, identifier)
WHERE deleted_at IS NULL — so the same handle can be re-assigned after a
soft-delete. `channel_type` is the ChannelType enum value (a stable slug that
crosses with conversations.ChannelAccount.channel_type — NOT a FK to a catalog).
`is_primary` marks the principal handle per (person_id, channel_type); enforced
in the service (marking a new primary unmarks the previous one).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.crm.models.person import Person


class PersonContactIdentifier(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "person_contact_identifier"
    __table_args__ = (
        # Partial UNIQUE: a live (channel_type, identifier) is globally unique
        # (single-tenant). After soft-delete the pair frees up for reassignment.
        # `sqlite_where` mirrors `postgresql_where` so the smoke (create_all on
        # sqlite, not alembic) reproduces the partial index — sin él, el test
        # "recrear tras soft-delete" fallaría en sqlite.
        Index(
            "uq_contact_identifier_channel_value",
            "channel_type",
            "identifier",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False, index=True
    )
    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)  # ChannelType
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    person: Mapped[Person] = relationship(back_populates="identifiers", lazy="raise")
