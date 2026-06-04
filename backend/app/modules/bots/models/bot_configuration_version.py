"""
BotConfigurationVersion = una versión INMUTABLE del comportamiento de un bot (prompt + provider +
model + params). Editar el prompt/params = crear una NUEVA versión (no in-place); la promoción se
hace con activate-version (setea bot_configuration.current_version_id). UNIQUE
(bot_configuration_id, version); el service asigna max+1. provider/external_webhook_* soportan el
ExternalBotEngine DIFERIDO (campos presentes, sin impl en el MVP).

`is_active` (soft-disable de la versión, ortogonal a "ser la current") NO es una columna nueva:
se reusa `ActiveMixin.active` (el schema lo expone como `is_active`). Una versión `active=false`
sigue existiendo (no se soft-deletea) — el BaseRepository no filtra por `active`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class BotConfigurationVersion(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "bot_configuration_version"
    __table_args__ = (
        # Un número de versión es único por bot. NO parcial: las versiones no se soft-deletean de
        # forma que liberen el número (son inmutables; `active` solo las deshabilita).
        Index(
            "uq_bot_config_version_number",
            "bot_configuration_id",
            "version",
            unique=True,
        ),
    )

    bot_configuration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_configuration.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)  # service asigna max+1
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # BotProvider
    model_name: Mapped[str] = mapped_column(
        String(120), nullable=False
    )  # default gpt-4.1-mini (schema)
    # {temperature?, max_tokens?, top_p?, ...} — schema libre por provider.
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    # Solo provider='external_webhook' (DIFERIDO). url requerida en ese caso (validación service).
    external_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_webhook_secret_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # changelog del prompt
