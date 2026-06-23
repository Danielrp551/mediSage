"""
Schemas de `CalendarConnection` (la cuenta OAuth de la clínica) + la respuesta del OAuth
start + la opción de proveedor para la UI de "Conectar X".

`is_active` mapea `ActiveMixin.active` (pausa manual); `sources_count` es denorm (batch
count) — NINGÚN denorm va en ALLOWED_FIELDS (lección cd10c78). `secret_name` NUNCA aparece
en un schema de salida (apunta a Secret Manager).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.calendar.enums import CalendarProvider, ConnectionStatus
from app.modules.calendar.schemas.source import CalendarSourceItem


class CalendarConnectionItem(BaseModel):
    """Fila de la lista de conexiones. `is_active` = ActiveMixin.active (pausa manual);
    sources_count = denorm (batch count). NINGÚN denorm en ALLOWED_FIELDS (cd10c78)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: CalendarProvider
    account_email: str
    display_name: str | None
    status: ConnectionStatus
    scopes: str | None = None
    last_checked_at: datetime | None = None
    sources_count: int = 0
    is_active: bool  # mapea active
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class CalendarConnectionDetail(CalendarConnectionItem):
    """Detalle: agrega los sources mapeados + el último error (observabilidad)."""

    sources: list[CalendarSourceItem]
    last_error: str | None = None


class OAuthStartResponse(BaseModel):
    """Respuesta de GET /oauth/{provider}/start — el front redirige a auth_url."""

    auth_url: str


class CalendarProviderOption(BaseModel):
    """Para la UI 'Conectar X' (botones header). value = CalendarProvider, label español."""

    value: CalendarProvider
    label: str
