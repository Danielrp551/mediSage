"""
BotTool = catálogo CONFIGURABLE de herramientas que un bot puede invocar (function calling /
tool use). target_service = '<module>.<service>.<function>' resuelto por TOOL_REGISTRY en
runtime (si el code no está registrado → TOOL_NOT_REGISTERED 404 en runtime, NO al boot —
permite seedear tools cuyo target aún no existe, ej. scheduling.* diferido). parameters_schema
= JSON Schema (subset común OpenAI/Anthropic). requires_confirmation = la tool muta algo
sensible (ej. set_lead_status) → el engine puede pedir confirmación (hardening; en el MVP se
loguea y se ejecuta). El M:N bot_configuration_tool decide qué tools ve cada bot.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class BotTool(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "bot_tool"
    __table_args__ = (
        # Partial UNIQUE: un `code` VIVO es único. Tras soft-delete libera el slug.
        Index(
            "uq_bot_tool_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(60), nullable=False)  # list_verticals, set_lead_status
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # la lee el LLM para decidir cuándo invocar
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_schema: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    # module.service.function (resuelto por TOOL_REGISTRY por `code` en runtime)
    target_service: Mapped[str] = mapped_column(String(120), nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # is_active de la spec = ActiveMixin.active (soft-disable de la tool).
