"""
CRM enums. NONE of these are DB catalogs — they are code-level value sets.
- ChannelType: closed set of contact channels. The slug crosses with
  conversations.ChannelAccount.channel_type (NOT a FK; a stable string contract).
- ActivityType: declared COMPLETE from day one (stable contract for the timeline)
  even though some values are emitted only when conversations/scheduling ship
  (see README §"Enum ActivityType por etapas"). Persisted as varchar(40).
- ActivityOutcome: optional qualifier for CALL_ATTEMPT activities.
"""

from __future__ import annotations

from enum import StrEnum


class ChannelType(StrEnum):
    whatsapp = "whatsapp"
    telegram = "telegram"
    web = "web"
    phone = "phone"
    email = "email"
    instagram = "instagram"
    facebook = "facebook"
    other = "other"


class ActivityType(StrEnum):
    # Emitted by the advisor (crm MVP).
    NOTE = "NOTE"
    CALL_ATTEMPT = "CALL_ATTEMPT"
    FOLLOW_UP_SCHEDULED = "FOLLOW_UP_SCHEDULED"
    FOLLOW_UP_COMPLETED = "FOLLOW_UP_COMPLETED"
    # Emitted by crm itself (system).
    STATUS_CHANGE = "STATUS_CHANGE"
    REASSIGNED = "REASSIGNED"
    CAMPAIGN_ATTRIBUTION = "CAMPAIGN_ATTRIBUTION"
    # Present in the enum NOW, emitted later by conversations/scheduling.
    MESSAGE_SENT = "MESSAGE_SENT"
    CONVERSATION_TAKEN = "CONVERSATION_TAKEN"
    CONVERSATION_RELEASED = "CONVERSATION_RELEASED"
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    APPOINTMENT_ATTENDED = "APPOINTMENT_ATTENDED"


class ActivityOutcome(StrEnum):
    successful = "successful"
    no_answer = "no_answer"
    busy = "busy"
    wrong_number = "wrong_number"
    not_interested = "not_interested"
    interested = "interested"
