"""
Schemas de las trazas de una cita: history de estado + change_log de columnas. Los
consume `AppointmentDetail`. `from_status`/`to_status` se denormalizan a
`AppointmentStatusOption` (badge). `changed_by_user` se hidrata batch (sin N+1).

`TimelineEntry` (entrelazado history+changelog para un solo hilo cronológico) llega en
F3 con la UI de detalle.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.scheduling.schemas.appointment_status import AppointmentStatusOption


class AppointmentStatusHistoryItem(BaseModel):
    """Una fila del timeline de estado. from_status null en la creación."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    appointment_id: str
    from_status: AppointmentStatusOption | None = None
    to_status: AppointmentStatusOption
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None


class AppointmentChangeLogItem(BaseModel):
    """Una fila del log de cambios in-place de columnas no-estado."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    appointment_id: str
    field_name: str
    previous_value: str | None
    new_value: str | None
    changed_at: datetime
    changed_by: str | None
    changed_by_user: UserAuditInfo | None = None
    reason: str | None
