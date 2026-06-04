from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.enums import BotType


class BotConfigurationCreate(BaseModel):
    # Slug: minúsculas, números y guion bajo (espeja el Zod del front + la UNIQUE parcial; evita
    # que la unicidad sea sorteable por casing vía llamada directa a la API).
    code: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    bot_type: BotType
    description: str | None = Field(default=None, max_length=4000)
    max_turns_per_conversation: int | None = Field(default=None, ge=1, le=1000)


class BotConfigurationUpdate(BaseModel):
    """Partial. `code` editable (re-dispara el guard de unicidad). El comportamiento
    (prompt/provider/model) NO se toca acá — eso es una NUEVA versión."""

    code: str | None = Field(default=None, min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    bot_type: BotType | None = None
    description: str | None = Field(default=None, max_length=4000)
    max_turns_per_conversation: int | None = Field(default=None, ge=1, le=1000)
    active: bool | None = None


class BotConfigurationOption(BaseModel):
    """Dropdown — GET /configurations/active (raw list). Lo consume el editor de canales
    (asociar un bot a un ChannelAccount) y la depuración."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    bot_type: BotType


class BotConfigurationItem(BaseModel):
    """Row de la tabla /configurations/list."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    bot_type: BotType
    description: str | None
    current_version_id: str | None
    current_version_number: int | None = None  # denormalizado (lookup de la versión vigente)
    max_turns_per_conversation: int | None
    version_count: int = 0  # denormalizado (cuántas versiones vivas tiene)
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class BotConfigurationDetail(BotConfigurationItem):
    """Full para el drawer + tab de versiones. Incluye la versión vigente expandida (si la hay).
    `tool_ids` (M:N) llega en F2 — en F1 SIEMPRE es []."""

    current_version: BotConfigurationVersionItem | None = None
    tool_ids: list[str] = Field(default_factory=list)  # ids de bot_tool asociados (M:N — F2)


class ActivateVersionRequest(BaseModel):
    """Body OPCIONAL de POST /configurations/{id}/activate-version/{vid}. El vid va en la URL;
    el body queda para futuros flags (ej. reset de estados en curso). Hoy vacío."""


# late import para el forward ref de current_version
from app.modules.bots.schemas.bot_configuration_version import (  # noqa: E402
    BotConfigurationVersionItem,
)

BotConfigurationDetail.model_rebuild()
