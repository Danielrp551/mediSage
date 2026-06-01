"""
Schemas Pydantic v2 de PersonContactIdentifier. El CRUD standalone vive anidado
bajo `/persons/{id}/identifiers`. Sin Ellipsis (`...`). Mensajes de validator en
inglés (van al detalle 422); el texto user-facing en español vive en el Zod del
frontend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType


class ContactIdentifierCreate(BaseModel):
    channel_type: ChannelType
    identifier: str = Field(min_length=1, max_length=255)
    is_primary: bool = False
    verified: bool = False


class ContactIdentifierUpdate(BaseModel):
    """Only the mutable fields. channel_type/identifier ARE editable (correcting a
    typo) but re-trigger the dedup guard. is_primary toggling unmarks the previous
    primary of the same channel."""

    channel_type: ChannelType | None = None
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    is_primary: bool | None = None
    verified: bool | None = None
    active: bool | None = None


class ContactIdentifierItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_id: str
    channel_type: ChannelType
    identifier: str
    is_primary: bool
    verified: bool
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
