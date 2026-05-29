"""
Vertical = top-level commercial area of the clinic (Dermatología, Estética
facial, Dental, ...). Slug `code` is stable and used by bots to classify
leads — never renamed once issued.

The hierarchy `Vertical -> Service -> Product` lives in this module. Other
modules consume `Vertical.id` via foreign keys (staff.doctor_vertical,
clinic.office_vertical, marketing.campaign.target_vertical_id).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.service import Service


class Vertical(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "vertical"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(60), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Children. `lazy="raise"` keeps accidental N+1 loud — counts are computed
    # with explicit batch queries in the service layer, not via this relation.
    services: Mapped[list[Service]] = relationship(back_populates="vertical", lazy="raise")
