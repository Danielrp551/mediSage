"""
Branch = a physical clinic site (sede). Root of the clinic hierarchy, no
domain FK. Carries a structured address (not free text) to enable future
"nearest branch" filtering in the bot and map integration. `code` is a
stable slug used in internal URLs and by bots — never renamed once issued.

`timezone` is an IANA name per branch (multi-country ready). It only matters
when scheduling resolves a local pattern time to a UTC instant; most instants
(closures, appointments) travel as timestamptz and convert in the browser.

The `offices` relationship is added in phase 2 alongside the Office model;
`offices_count` is hardcoded to 0 until then (phase 1 has no Office table).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Branch(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "branch"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # ── Structured address ──
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="PE")
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Geo (optional) ──
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)

    # ── Contact ──
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Time ──
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="America/Lima")
