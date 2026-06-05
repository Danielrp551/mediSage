"""
Schemas Pydantic v2 de BotTool (catálogo de herramientas invocables) + ConfigurationToolsUpdate
(body del set bulk del M:N). `is_registered` es denormalizado (lo computa el service contra el
TOOL_REGISTRY en memoria, por `code`) → NO es columna, NO va en ALLOWED_FIELDS. `code` NO es
editable tras crear (es la clave que cruza con el registry). Mensajes de validator en inglés (422);
el copy en español lo pone el Zod del front.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo


class BotToolCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)  # JSON Schema (subset común)
    target_service: str = Field(min_length=1, max_length=120)  # module.service.function
    requires_confirmation: bool = False


class BotToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    parameters_schema: dict[str, Any] | None = None
    target_service: str | None = Field(default=None, min_length=1, max_length=120)
    requires_confirmation: bool | None = None
    active: bool | None = None
    # `code` NO editable tras crear (es la clave que cruza con TOOL_REGISTRY).


class BotToolOption(BaseModel):
    """Dropdown / multiselect del editor de tools por bot."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    requires_confirmation: bool


class BotToolItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str
    target_service: str
    requires_confirmation: bool
    is_registered: bool = False  # denormalizado: code ∈ TOOL_REGISTRY (lo computa el service)
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class BotToolDetail(BotToolItem):
    parameters_schema: dict[str, Any]


class ConfigurationToolsUpdate(BaseModel):
    """Body de PUT /configurations/{id}/tools — set bulk del M:N (reemplaza el conjunto)."""

    tool_ids: list[str] = Field(default_factory=list)
