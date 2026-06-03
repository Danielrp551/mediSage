"""
conversations enums. NONE of these are DB catalogs — they are code-level value
sets (`StrEnum`, ruff UP042). Las columnas que los referencian son `varchar`
planas: Pydantic valida contra el enum, la BD almacena el slug.

`ChannelType` NO se redefine acá — se REUSA de `crm.enums` (single source of
truth; el slug cruza con `crm.PersonContactIdentifier.channel_type`). conversations
hace `from app.modules.crm.enums import ChannelType`. **NO duplicar.**

F1 usa `ChannelType` (reuse) para `ChannelAccount.channel_type`. El resto de los
enums (Conversation/Message) se declaran ya (son inertes en F1, contratos estables
del código) y los consumen F2/F3; F1 NO crea modelos de conversación/mensaje.
"""

from __future__ import annotations

from enum import StrEnum

# NB: ChannelType is imported from crm — `from app.modules.crm.enums import ChannelType`.


class ConversationStatus(StrEnum):
    open = "open"
    closed = "closed"


class AssigneeType(StrEnum):
    bot = "bot"
    advisor = "advisor"
    unassigned = "unassigned"


class MessageDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class SenderType(StrEnum):
    contact = "contact"
    bot = "bot"
    advisor = "advisor"
    system = "system"


class ContentType(StrEnum):
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"
    document = "document"
    location = "location"
    sticker = "sticker"
    contact_card = "contact_card"
    system_notification = "system_notification"


class AttachmentType(StrEnum):
    image = "image"
    audio = "audio"
    video = "video"
    document = "document"
    location = "location"
    sticker = "sticker"
    contact_card = "contact_card"


class MessageExternalStatus(StrEnum):
    """Valores conocidos de `message.external_status`. La columna es varchar libre
    (el proveedor puede devolver otros); este enum es el contrato para los badges
    de la UI."""

    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"
