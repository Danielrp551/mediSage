"""
Schemas del MENSAJE. DOBLE propósito (CQRS / ADR-011):
1. Shape del DOC Firestore `conversations/{cid}/messages/{mid}` (snake_case — alineado
   a propósito con el contrato de la API; el browser lo lee tal cual vía onSnapshot).
2. Shape del envelope del endpoint FALLBACK `POST /{id}/messages/list` (que lee Firestore
   server-side vía Admin SDK).

NO mapea una tabla Postgres (el stream vive en Firestore). `id` = el `mid` (= doc-id
Firestore = wamid/uuid). `created_on` ↔ `created_at` del doc (el service mapea el campo
del doc al schema). Convenciones: sin Ellipsis; mensajes de validator en inglés (422);
copy user-facing en español en el Zod del front.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.enums import (
    AttachmentType,
    ContentType,
    MessageDirection,
    SenderType,
)


class MessageAttachmentItem(BaseModel):
    """Shape de un adjunto del mensaje — sub-objeto `attachments[]` del DOC Firestore (NO
    una tabla Postgres). Sin processing en el MVP → en la práctica lista vacía hasta F4
    (texto primero). En F4 cada adjunto apunta a un binario en GCS (url firmada)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    message_id: str
    attachment_type: AttachmentType
    url: str | None = None  # F4: URL firmada de GCS
    mime_type: str | None = None
    size_bytes: int | None = None
    duration_sec: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    address_label: str | None = None
    original_filename: str | None = None
    external_media_id: str | None = None
    metadata: dict[str, Any] | None = None  # campo libre del doc Firestore


class MessageItem(BaseModel):
    """Contrato del mensaje (doc Firestore + envelope del fallback `/messages/list`)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    direction: MessageDirection
    sender_type: SenderType
    sender_user_id: str | None = None  # raw FK lógica (advisor); null en contact/bot/system
    sender_user: UserAuditInfo | None = None  # denormalizado; null salvo sender_type='advisor'
    content_type: ContentType
    content: str | None = None
    external_id: str | None = None
    external_status: str | None = None  # free varchar; la UI mapea a MessageExternalStatus
    sent_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    attachments: list[MessageAttachmentItem] = Field(default_factory=list)
    created_on: datetime


class MessageSendRequest(BaseModel):
    """Body de POST /conversations/{id}/messages (outbound, F3). MVP solo text → el
    validator rechaza otros content_type con 422 (el service además puede levantar
    UNSUPPORTED_CONTENT_TYPE 400); attachments en F4."""

    content: str = Field(min_length=1, max_length=4096)
    content_type: ContentType = ContentType.text

    @model_validator(mode="after")
    def _text_only_mvp(self) -> MessageSendRequest:
        if self.content_type != ContentType.text:
            raise ValueError("only text content_type is supported in the MVP")
        return self
