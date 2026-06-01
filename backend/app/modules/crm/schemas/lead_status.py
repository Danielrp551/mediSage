"""
Schemas Pydantic v2 del catálogo LeadStatus + la matriz de transiciones (ADR-008).
Espejo de `frontend/src/types/crm.types.ts` (contrato front autoritativo, F0).

- Create valida `is_won ⟹ is_final` (WON_REQUIRES_FINAL). La regla "exactamente un
  is_initial" NO se valida acá (cruza con los demás registros) → la chequea el
  service (MULTIPLE_INITIAL_STATUS).
- `code` es inmutable (slug estable) → no se declara en Update.
- `StatusTransitionUpdate {to_ids}` es el body de PUT /{id}/transitions (REEMPLAZA
  las aristas de salida). `TransitionTargets {from_id, to}` es la respuesta de
  GET/PUT /{id}/transitions (las aristas resueltas a Options).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.admin.schemas.audit import UserAuditInfo


class LeadStatusCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool = False
    is_final: bool = False
    is_won: bool = False
    display_order: int = 0

    # Nota: `is_won ⟹ is_final` (WON_REQUIRES_FINAL) NO se valida acá. Un
    # model_validator devolvería 422; la spec de errores y los tests exigen
    # **400 + code=WON_REQUIRES_FINAL** y de forma CONSISTENTE en create y update
    # → la regla la aplica el service (uniforme para ambos paths).


class LeadStatusUpdate(BaseModel):
    """`code` es inmutable (slug estable) → no se declara. `is_won ⟹ is_final` se
    revalida en el service sobre el merge (los campos parciales no permiten un
    model_validator confiable acá)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool | None = None
    is_final: bool | None = None
    is_won: bool | None = None
    display_order: int | None = None
    active: bool | None = None


class LeadStatusItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    is_initial: bool
    is_final: bool
    is_won: bool
    display_order: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class LeadStatusOption(BaseModel):
    """Shape para dropdowns / badges — GET /lead-statuses/active (lista cruda)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_initial: bool = False
    is_final: bool = False
    is_won: bool = False


class StatusTransitionUpdate(BaseModel):
    """Body de PUT /lead-statuses/{id}/transitions — REEMPLAZA las aristas de salida
    de un estado por exactamente estos destinos. Reusado por customer-statuses."""

    to_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_dupes(self) -> StatusTransitionUpdate:
        if len(self.to_ids) != len(set(self.to_ids)):
            raise ValueError("to_ids must not contain duplicates")
        return self


class TransitionTargets(BaseModel):
    """Respuesta de GET/PUT /lead-statuses/{id}/transitions: los estados a los que
    {from_id} PUEDE ir (aristas de salida resueltas a Options). Espeja
    `TransitionTargets` de crm.types.ts."""

    from_id: str
    to: list[LeadStatusOption]
