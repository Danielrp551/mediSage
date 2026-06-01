"""
LeadStatus — catálogo configurable de estados del hilo lead (ADR-008). En BD para
que admin renombre / agregue estados sin deploy. Flags:
- is_initial: estado por defecto al crear un lead. EXACTAMENTE uno por catálogo
  (validado en el service: MULTIPLE_INITIAL_STATUS).
- is_final: terminal (al entrar, la fila PersonLeadStatus se soft-deletea — F3).
- is_won: terminal-positivo; solo válido cuando is_final=true (WON_REQUIRES_FINAL).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class LeadStatus(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "lead_status"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # hex para badges
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_won: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
