"""
Schemas Pydantic v2 del catálogo CustomerStatus + sus targets de transición.
Idéntico a `lead_status.py` MENOS `is_won` (y sin `_won_requires_final`). Reusa
`StatusTransitionUpdate` (el body {to_ids} es agnóstico al catálogo). Espeja
`CustomerStatusItem`/`CustomerStatusOption`/`CustomerTransitionTargets` de
`frontend/src/types/crm.types.ts`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.admin.schemas.audit import UserAuditInfo


class CustomerStatusCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool = False
    is_final: bool = False
    display_order: int = 0


class CustomerStatusUpdate(BaseModel):
    """`code` es inmutable (slug estable) → no se declara."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    is_initial: bool | None = None
    is_final: bool | None = None
    display_order: int | None = None
    active: bool | None = None


class CustomerStatusItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    is_initial: bool
    is_final: bool
    display_order: int
    active: bool
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class CustomerStatusOption(BaseModel):
    """Shape para dropdowns / badges — GET /customer-statuses/active (lista cruda)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_initial: bool = False
    is_final: bool = False


class CustomerTransitionTargets(BaseModel):
    """Respuesta de GET/PUT /customer-statuses/{id}/transitions (aristas de salida
    resueltas a Options). Espeja `CustomerTransitionTargets` de crm.types.ts."""

    from_id: str
    to: list[CustomerStatusOption]
