"""
ChannelAccount = una cuenta de canal de la clínica (config + referencia al
secreto). Multi-cuenta: N números de WhatsApp sin redeploy (cada uno con su
`secret_name`). El SECRETO NUNCA vive en BD ni se expone en la API — `secret_name`
apunta a GCP Secret Manager y el secret_resolver lo resuelve en runtime (ADR-010).
`channel_type` es el valor de `crm.ChannelType` (reuse; NO un FK a un catálogo).
`bot_configuration_id` / `default_campaign_id` son FKs forward (ADR-009):
`varchar(36)` + index, SIN FK/relationship (las tablas `bot_configuration`/
`campaign` aún no existen; el módulo dueño agrega la constraint de forma aditiva).
Hoy ambas SIEMPRE NULL.
"""

from __future__ import annotations

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import (
    ActiveMixin,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class ChannelAccount(PrimaryKeyMixin, ActiveMixin, SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "channel_account"
    __table_args__ = (
        # Partial UNIQUE: a LIVE (channel_type, external_identifier) is globally
        # unique (single-tenant). After soft-delete the pair frees up for
        # re-registration. Dialect-agnóstico: postgresql_where + sqlite_where para
        # que el smoke (create_all en sqlite) reproduzca el índice parcial.
        Index(
            "uq_channel_account_type_external",
            "channel_type",
            "external_identifier",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)  # crm.ChannelType (reuse)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    # Referencia al secreto por-cuenta en GCP Secret Manager (resuelto en runtime).
    # NULL = fallback a env (local/dev). El SECRETO en sí jamás se guarda acá.
    secret_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Challenge de verificación de Meta (GET webhook). No es secreto duro (Meta lo
    # envía y lo comparamos) → columna directa, editable por el admin.
    webhook_verify_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Id del número en WhatsApp Cloud API → construye la URL de envío
    # /{phone_number_id}/messages.
    phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # FK forward a bots.bot_configuration (ADR-009) — bot por defecto del canal. Hoy NULL.
    bot_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # FK forward a marketing.campaign (ADR-009) — campaña de atribución que se pasa a
    # find_by_identifier_or_create(campaign_id=...). Hoy NULL.
    default_campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
