"""
Office = a consulting room (consultorio) inside a Branch. Declares which
catalog Verticals it is fit to host (M:N office_vertical) so scheduling can
filter offices apt for a requested product. `code` is unique per branch
((branch_id, code)) — the same code can repeat across branches.

The M:N `verticals` is uni-directional: catalog.Vertical does NOT declare
`offices` (keeps catalog decoupled from clinic — clinic depends on catalog,
not the reverse). Soft-deleted verticals stay in the association table and are
filtered at query time (see repository `get_full` / `count_apt_verticals_map`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.clinic.models.associations import office_vertical
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.catalog.models.vertical import Vertical
    from app.modules.clinic.models.branch import Branch


class Office(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "office"
    __table_args__ = (UniqueConstraint("branch_id", "code", name="uq_office_branch_code"),)

    branch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("branch.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    room_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    branch: Mapped[Branch] = relationship(back_populates="offices", lazy="raise")

    # M:N with catalog.Vertical. `lazy="raise"` — the apt verticals are loaded
    # explicitly with selectinload + a deleted_at filter (see repository).
    verticals: Mapped[list[Vertical]] = relationship(secondary=office_vertical, lazy="raise")
