"""
Schemas Pydantic v2 de `ChannelAccount`. Variantes: Create / Update (partial) /
Item (row de la tabla) / Detail (drawer) / Option (dropdowns).

⚠ El SECRETO nunca viaja a un schema: `Item`/`Detail` exponen solo `secret_name`
(el NOMBRE del recurso, NO su valor) + el flag derivado `credentials_configured`
(= secret_name is not None). El `access_token`/`app_secret` viven solo en GCP
Secret Manager y los resuelve `get_credentials` server-side (ADR-010).

`channel_type` reusa `crm.enums.ChannelType`. Convenciones del template: sin
Ellipsis en `Field(...)`; mensajes de validator en inglés (van al 422); copy
user-facing en español en el Zod del front; `from_attributes=True` en los
`Item`/`Detail`/`Option`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType  # REUSE — single source of truth


class ChannelAccountCreate(BaseModel):
    channel_type: ChannelType
    name: str = Field(min_length=1, max_length=120)
    external_identifier: str = Field(min_length=1, max_length=255)
    secret_name: str | None = Field(default=None, max_length=255)
    webhook_verify_token: str | None = Field(default=None, max_length=255)
    phone_number_id: str | None = Field(default=None, max_length=64)
    # bot_configuration_id / default_campaign_id NO se exponen en el MVP (forward
    # FKs, siempre NULL; los expondrá bots/marketing).


class ChannelAccountUpdate(BaseModel):
    """Partial. `channel_type`/`external_identifier` SON editables (corregir un
    alta) pero re-disparan el guard de unicidad. El SECRETO no se gestiona acá."""

    channel_type: ChannelType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    external_identifier: str | None = Field(default=None, min_length=1, max_length=255)
    secret_name: str | None = Field(default=None, max_length=255)
    webhook_verify_token: str | None = Field(default=None, max_length=255)
    phone_number_id: str | None = Field(default=None, max_length=64)
    active: bool | None = None


class ChannelAccountOption(BaseModel):
    """Dropdown / filtro — GET /channel-accounts/active (lista cruda). Lo consume el
    inbox (chip de canal) y los espejos en ConversationListItem.channel_account."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    channel_type: ChannelType
    external_identifier: str


class ChannelAccountItem(BaseModel):
    """Row de la tabla /channel-accounts/list."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    channel_type: ChannelType
    name: str
    external_identifier: str
    phone_number_id: str | None
    # NUNCA el secreto: solo flags derivados de si está configurado.
    credentials_configured: bool  # = secret_name is not None (espejo de types.ts)
    has_verify_token: bool  # = webhook_verify_token is not None
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class ChannelAccountDetail(ChannelAccountItem):
    """Full para el drawer de edición. EXPONE `secret_name` (el NOMBRE del secreto,
    NO su valor) y `webhook_verify_token` (no es secreto duro: lo envía Meta y se
    compara). NUNCA expone access_token/app_secret — esos viven solo en Secret
    Manager y los resuelve get_credentials server-side."""

    secret_name: str | None
    webhook_verify_token: str | None
    bot_configuration_id: str | None = None
    default_campaign_id: str | None = None
