"""
Person = the root identity of a CRM contact (ADR-003). Holds ONLY identity and
basic profile data; the commercial threads (lead / customer), the owner, the
identifiers and the activity timeline live in CHILD tables. No phone/email
column here — those live in PersonContactIdentifier (multichannel, dedup-able).
No medical data (MVP).

A Person may have a PersonLeadStatus AND a PersonCustomerStatus at the same time
(active customer who becomes a lead of another campaign — ADR-003), only one of
them, or none.

⚠ F1 subset: solo se declara la relación `identifiers`. Las relaciones
`lead_status`/`customer_status`/`assignment` apuntan a modelos
(PersonLeadStatus/PersonCustomerStatus/LeadAssignment) que aún NO existen —
declararlas reventaría el mapper al importar. Se agregan en F3/F4 cuando esos
modelos existan (mismo patrón que staff F1 difirió `availability`).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.crm.models.person_contact_identifier import PersonContactIdentifier


class Person(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "person"

    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    second_last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)  # free text, no enum
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Children. All lazy="raise" — loaded explicitly with selectinload in the repo.
    identifiers: Mapped[list[PersonContactIdentifier]] = relationship(
        back_populates="person", lazy="raise"
    )
    # lead_status/customer_status/assignment → F3/F4 (sus modelos no existen en F1).
