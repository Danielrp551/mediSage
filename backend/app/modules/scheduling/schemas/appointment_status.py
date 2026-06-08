"""
Schemas Pydantic v2 del catálogo AppointmentStatus + la matriz de transiciones
(ADR-008). Espejo de `frontend/src/types/scheduling.types.ts` (contrato front
autoritativo, shippeado en F0).

Espeja `crm.lead_status` SIN `is_won` (no aplica a citas). Decisiones de contrato:
- `code` MAYÚSCULAS, inmutable → no se declara en Update. NO lleva validator de
  pattern en el backend (igual que crm.LeadStatusCreate): el Zod del front impone
  el casing en MAYÚSCULAS client-side. La única regla de catálogo es "exactamente un
  is_initial" (MULTIPLE_INITIAL_STATUS), validada en el SERVICE (cruza con los demás
  registros → 400 + code consistente, no 422 de Pydantic).
- `StatusTransitionUpdate {to_ids}` = body de PUT /{id}/transitions (REEMPLAZA las
  aristas de salida). `TransitionTargets {from_id, to}` = respuesta de GET/PUT
  /{id}/transitions (las aristas resueltas a Options). Espeja crm.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class AppointmentStatusCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool = False
    is_final: bool = False
    is_active_attention: bool = False
    display_order: int = 0


class AppointmentStatusUpdate(BaseModel):
    """`code` es inmutable (slug estable) → no se declara."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool | None = None
    is_final: bool | None = None
    is_active_attention: bool | None = None
    display_order: int | None = None
    active: bool | None = None


class AppointmentStatusItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    is_initial: bool
    is_final: bool
    is_active_attention: bool
    display_order: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class AppointmentStatusOption(BaseModel):
    """Shape para dropdowns / badges — GET /appointment-statuses/active (lista cruda).
    Es el shape que el backend denormaliza como badge en Appointment (F2)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_initial: bool = False
    is_final: bool = False
    is_active_attention: bool = False


class StatusTransitionUpdate(BaseModel):
    """Body de PUT /appointment-statuses/{id}/transitions — REEMPLAZA las aristas de
    salida de un estado por exactamente estos destinos."""

    to_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_dupes(self) -> StatusTransitionUpdate:
        if len(self.to_ids) != len(set(self.to_ids)):
            raise ValueError("to_ids must not contain duplicates")
        return self


class TransitionTargets(BaseModel):
    """Respuesta de GET/PUT /appointment-statuses/{id}/transitions: los estados a los
    que {from_id} PUEDE ir (aristas de salida resueltas a Options). Espeja
    `TransitionTargets` de scheduling.types.ts."""

    from_id: str
    to: list[AppointmentStatusOption]
