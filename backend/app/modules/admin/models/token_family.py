"""
A refresh-token "family" represents one login session. The row is created
on login and updated on every refresh (rotating `current_jti`). Logout
or reuse detection sets `revoked_at`.

Refresh-rotation contract:
  • Each refresh token carries `family` and `jti` claims.
  • On `/auth/refresh`, the service looks up the family row and verifies
    the incoming `jti` matches `current_jti`. Match → rotate (issue new
    jti, update column). Mismatch → reuse → revoke family → reject.
  • `revoked_at IS NOT NULL` short-circuits any refresh on the family.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import PrimaryKeyMixin
from app.shared.utils import utc_now


class TokenFamily(PrimaryKeyMixin, Base):
    __tablename__ = "token_family"

    family_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_jti: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
