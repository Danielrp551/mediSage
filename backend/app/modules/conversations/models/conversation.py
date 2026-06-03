"""
Conversation = el hilo de mensajería de una Person en un canal (control plane /
fuente de verdad, ADR-011 CQRS). El stream de MENSAJES vive en Firestore (read-model
real-time), NO en Postgres; esta tabla guarda el estado relacional/operativo: a quién
está asignada, su estado (open/closed), los FKs a Person/ChannelAccount/User y los
denormalizados last_message_*/unread_count para la bandeja (inbox) sin N+1.

A lo sumo UNA conversación ABIERTA por (person, channel) — el UNIQUE PARCIAL
(`status='open' AND deleted_at IS NULL`) hace que `find_or_create_open` sea
determinístico. Cerrar (`status='closed'`) NO soft-deletea: la conversación queda en
el historial y se puede reabrir; `deleted_at` queda para una eliminación lógica real.

Invariantes (validados en el SERVICE, no en la BD): assignee_type='advisor' ⇔
assignee_user_id NOT NULL; assignee_type ∈ {bot, unassigned} ⇒ assignee_user_id NULL.
Las FKs a person/user son reales (crm/admin existen); bot_configuration_id es forward
(ADR-009, varchar sin constraint — bots #6 aún no existe).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Conversation(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = (
        # A lo sumo UNA conversación abierta por (person, channel) — el dedup que hace
        # find_or_create_open determinístico. Parcial: las cerradas/soft-deleted lo liberan.
        # Dialect-agnóstico: postgresql_where + sqlite_where para que el smoke (create_all)
        # reproduzca el índice parcial COMPUESTO (status='open' AND deleted_at IS NULL).
        Index(
            "uq_conversation_person_channel_open",
            "person_id",
            "channel_account_id",
            unique=True,
            postgresql_where=text("status = 'open' AND deleted_at IS NULL"),
            sqlite_where=text("status = 'open' AND deleted_at IS NULL"),
        ),
    )

    channel_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channel_account.id"), nullable=False, index=True
    )
    # FK real → person.id (crm existe). NULL solo en la ventana corta antes de resolver
    # (en práctica siempre poblado tras find_or_create_open).
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ConversationStatus
    assignee_type: Mapped[str] = mapped_column(String(20), nullable=False)  # AssigneeType
    # FK real → user.id. NOT NULL ⟺ assignee_type='advisor' (invariante de service).
    assignee_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=True, index=True
    )
    # Forward FK a bots.bot_configuration (ADR-009) — bot efectivo. Hoy NULL.
    bot_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Denormalizados para el inbox (sort + preview + badge).
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
