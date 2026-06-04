"""
BotConfiguration = un bot configurable de la clínica (preventa, postventa_dental, ...). Es el
contenedor; el comportamiento concreto (prompt/provider/model/params) vive en sus
BotConfigurationVersion (versionado inmutable). current_version_id apunta a la versión VIGENTE
(NULL = sin versión → no usable). FK real a bot_configuration_version (forward dentro del mismo
módulo: la columna se crea en 0017 y la FK se agrega tras crear bot_configuration_version, también
en 0017). max_turns_per_conversation (nullable) = guard opcional de costo (None = sin límite).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class BotConfiguration(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "bot_configuration"
    __table_args__ = (
        # Partial UNIQUE: un `code` VIVO es único (single-tenant). Tras soft-delete libera el slug.
        Index(
            "uq_bot_configuration_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # slug: preventa, postventa_dental
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bot_type: Mapped[str] = mapped_column(String(20), nullable=False)  # BotType
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Versión vigente. FK real → bot_configuration_version (se agrega tras crear esa tabla, misma
    # migración 0017). NULL = sin versión activa (no usable).
    current_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bot_configuration_version.id"), nullable=True, index=True
    )
    # Guard opcional de costo: máximo de turnos del bot por conversación (None = sin límite).
    max_turns_per_conversation: Mapped[int | None] = mapped_column(Integer, nullable=True)
