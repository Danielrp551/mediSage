"""
User aggregate.

`Person` from KAM Digital was folded in: identity + auth + profile live on
one table. If a future use case needs service accounts (no profile), add
nullable profile columns or split via single-table inheritance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.admin.models.associations import user_permission, user_role
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.admin.models.permission import Permission
    from app.modules.admin.models.role import Role


class User(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "user"

    # ── Auth ──
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Profile ──
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    second_last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ── RBAC ──
    roles: Mapped[list["Role"]] = relationship(
        secondary=user_role, back_populates="users", lazy="selectin"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=user_permission, back_populates="users", lazy="selectin"
    )

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        if self.second_last_name:
            parts.append(self.second_last_name)
        return " ".join(parts)

    def effective_permission_codes(self) -> list[str]:
        """Direct permissions + permissions inherited through roles."""
        codes: set[str] = {p.code for p in self.permissions}
        for r in self.roles:
            codes.update(p.code for p in r.permissions)
        return sorted(codes)
