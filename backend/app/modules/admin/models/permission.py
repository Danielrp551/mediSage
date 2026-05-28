from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.admin.models.associations import role_permission, user_permission
from app.shared.base_model import ActiveMixin, PrimaryKeyMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.admin.models.role import Role
    from app.modules.admin.models.user import User


class Permission(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    module: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permission, back_populates="permissions", lazy="raise"
    )
    users: Mapped[list[User]] = relationship(
        secondary=user_permission, back_populates="permissions", lazy="raise"
    )
