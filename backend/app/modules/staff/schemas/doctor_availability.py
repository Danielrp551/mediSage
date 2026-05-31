"""
Schemas Pydantic v2 de DoctorAvailability (bloque concreto por fecha). Variantes:
- DoctorAvailabilityCreate: un bloque (validator closes_at > opens_at, espeja el CHECK).
- DoctorAvailabilityBulkCreate: body del POST (alta masiva "llenar varios días").
- DoctorAvailabilityUpdate: editar un bloque (mover/redimensionar; todo opcional).
- DoctorAvailabilityItem: fila de respuesta, con branch_name/office_code/office_name
  denormalizados (render directo en la grilla, sin join).

Sin Ellipsis. Mensajes de validator en inglés (van al detalle 422); el texto
user-facing en español vive en el Zod del frontend.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class DoctorAvailabilityCreate(BaseModel):
    """Un bloque concreto. Usado en el alta masiva y como forma editable.
    `closes_at > opens_at` espeja el CHECK de BD."""

    branch_id: str = Field(min_length=1)
    office_id: str = Field(min_length=1)
    date: date_type
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def _closes_after_opens(self) -> DoctorAvailabilityCreate:
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be later than opens_at")
        return self


class DoctorAvailabilityBulkCreate(BaseModel):
    """Body del POST /doctors/{id}/availability — alta masiva ("llenar varios a
    la vez"). El service valida los invariantes para todo el set entrante Y contra
    los bloques existentes del doctor en esas fechas."""

    blocks: list[DoctorAvailabilityCreate] = Field(min_length=1)


class DoctorAvailabilityUpdate(BaseModel):
    """Editar UN bloque (mover/redimensionar). Todos los campos opcionales; el
    chequeo cross-field corre en el service sobre el bloque mergeado."""

    branch_id: str | None = Field(default=None, min_length=1)
    office_id: str | None = Field(default=None, min_length=1)
    date: date_type | None = None
    opens_at: time | None = None
    closes_at: time | None = None


class DoctorAvailabilityItem(BaseModel):
    """Un bloque en una respuesta GET. Denormaliza branch_name/office_code/
    office_name para render directo en la grilla (sin join en el front)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    doctor_id: str
    branch_id: str
    branch_name: str  # denormalizado
    office_id: str
    office_code: str  # denormalizado
    office_name: str  # denormalizado
    date: date_type
    opens_at: time
    closes_at: time
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None
