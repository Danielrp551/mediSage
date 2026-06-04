from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.bots.enums import BotProvider

DEFAULT_MODEL = "gpt-4.1-mini"  # default OpenAI (reconciliación §0.2)


class BotConfigurationVersionCreate(BaseModel):
    """Crear una NUEVA versión de un bot (no se edita in-place). El número de versión lo asigna
    el service (max+1). provider='external_webhook' ⇒ external_webhook_url requerida."""

    system_prompt: str = Field(min_length=1, max_length=20000)
    provider: BotProvider = BotProvider.openai
    model_name: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    external_webhook_url: str | None = Field(default=None, max_length=500)
    external_webhook_secret_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _external_webhook_requires_url(self) -> BotConfigurationVersionCreate:
        # Validación de FORMA (422). El service repite la regla como BadRequestException 400
        # (EXTERNAL_WEBHOOK_URL_REQUIRED) para tener el `code` en el contrato.
        if self.provider == BotProvider.external_webhook and not self.external_webhook_url:
            raise ValueError("external_webhook_url is required when provider is external_webhook")
        return self


class BotConfigurationVersionItem(BaseModel):
    """Row liviano (lista de versiones; NO incluye el system_prompt completo en la tabla)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    bot_configuration_id: str
    version: int
    provider: BotProvider
    model_name: str
    is_active: bool  # = ActiveMixin.active (soft-disable de la versión; ver model docstring)
    is_current: bool = False  # denormalizado: id == bot_configuration.current_version_id
    notes: str | None
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None


class BotConfigurationVersionDetail(BotConfigurationVersionItem):
    """Full (editor de versión / preview): incluye el prompt y los params."""

    system_prompt: str
    parameters: dict[str, Any]
    external_webhook_url: str | None
    external_webhook_secret_name: str | None  # NO expone el secreto, solo su NOMBRE
