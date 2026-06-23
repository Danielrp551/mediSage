"""
CalendarConnection = una cuenta OAuth de la clínica (Google/Microsoft). Típicamente
1-2 filas (la cuenta de Google de la clínica + la de Outlook). Los TOKENS NO están
aquí: `secret_name` apunta al secreto `medisage-calendar-{id}-{env}` en Secret Manager
con el JSON {access_token, refresh_token, expiry, scopes} (ADR-010 extendido).

`status` (ConnectionStatus) da salud: `needs_reauth` cuando el refresh devuelve
`invalid_grant`. `active` (ActiveMixin, expuesto is_active) = pausa manual; deleted_at
(SD) = desconectar. UNIQUE PARCIAL (provider, account_email) WHERE deleted_at IS NULL:
no conectar 2 veces la misma cuenta viva; tras desconectar, el par se libera.

`sources` 1:N con lazy="raise" (se carga con selectinload en el detalle, nunca por
accidente — N+1 ruidoso). FK cross-módulo a branch vive en CalendarSource, no aquí.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.modules.calendar.models.calendar_source import CalendarSource


class CalendarConnection(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "calendar_connection"
    __table_args__ = (
        # UNIQUE PARCIAL: (provider, account_email) VIVA es única (single-tenant).
        # Tras soft-delete el par se libera para re-conectar. Dialect-agnóstico
        # (postgresql_where + sqlite_where) para que el smoke (create_all en sqlite)
        # reproduzca el índice parcial — molde conversations.ChannelAccount.
        Index(
            "uq_calendar_connection_provider_email",
            "provider",
            "account_email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    # CalendarProvider value (google|microsoft).
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Identidad de la cuenta (de Google userinfo / Graph /me).
    account_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Etiqueta amigable (default = account_email, resuelto en el service si llega NULL).
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Puntero a Secret Manager (medisage-calendar-{id}-{env}). NUNCA el token en sí.
    secret_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # ConnectionStatus value; default connected al crear.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="connected")
    # Scopes concedidos (auditoría, space-separated).
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Última validación/refresh OK (observabilidad UI "Última revisión: hace N").
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Último error de refresh/list (observabilidad, NO bloquea).
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 1:N. lazy="raise": el detalle usa selectinload(CalendarConnection.sources).
    sources: Mapped[list[CalendarSource]] = relationship(
        back_populates="connection", lazy="raise", cascade="all, delete-orphan"
    )
