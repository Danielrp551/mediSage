"""
M:N entre BotConfiguration y BotTool: qué tools puede invocar cada bot. PK compuesta. Igual
patrón que admin/associations.py (Table en un solo archivo para que SQLAlchemy lo vea antes de
los modelos). ondelete CASCADE: borrar (hard) un bot/tool limpia las filas del M:N; el borrado
de negocio es soft-delete (deleted_at) en las entidades, no toca esta tabla.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

bot_configuration_tool = Table(
    "bot_configuration_tool",
    Base.metadata,
    Column(
        "bot_configuration_id",
        String(36),
        ForeignKey("bot_configuration.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "bot_tool_id",
        String(36),
        ForeignKey("bot_tool.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
