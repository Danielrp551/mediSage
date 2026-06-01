"""
Schemas Pydantic v2 de Person (+ PersonContactIdentifier anidado en el create).
Variantes:
- PersonContactIdentifierInput: identifier inicial inline en PersonCreate.
- PersonCreate / PersonUpdate: input de creación (con identifiers nested) y de
  actualización parcial de identidad.
- PersonItem: fila paginada, con `full_name`/`primary_identifier` denormalizados
  + los resúmenes `lead_status`/`customer_status`/`assigned_advisor`/
  `last_activity_at` (contrato estable que espeja types/crm.types.ts).
- PersonDetail: Item + campos de perfil + identifiers[] resueltos.
- PersonOption: dropdowns / selects.

⚠ F1: los resúmenes lead/customer/assignment NO tienen tabla fuente todavía
(F3/F4) — el service SIEMPRE los deja en None. Se declaran ahora para que el
contrato (y el espejo TS) no cambie de shape cuando lleguen esas fases.

Sin Ellipsis (`...`). Mensajes de validator en inglés (van al detalle 422); el
texto user-facing en español vive en el Zod del frontend.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.crm.enums import ChannelType
from app.modules.crm.schemas.contact_identifier import ContactIdentifierItem


class PersonContactIdentifierInput(BaseModel):
    """Initial identifier supplied INLINE in PersonCreate (optional list). The
    standalone CRUD lives in contact_identifier.py."""

    channel_type: ChannelType
    identifier: str = Field(min_length=1, max_length=255)
    is_primary: bool = False
    verified: bool = False


class PersonCreate(BaseModel):
    """Creates a Person and (optionally) its initial identifiers in one tx. Does
    NOT create a lead automatically (that's POST /lead-status or
    find_by_identifier_or_create)."""

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    birth_date: date_type | None = None
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    identifiers: list[PersonContactIdentifierInput] = Field(default_factory=list)

    @field_validator("identifiers")
    @classmethod
    def _no_dup_identifiers(
        cls, v: list[PersonContactIdentifierInput]
    ) -> list[PersonContactIdentifierInput]:
        seen = {(i.channel_type, i.identifier) for i in v}
        if len(seen) != len(v):
            raise ValueError("identifiers must not contain duplicate (channel_type, identifier)")
        # At most one primary per channel_type in the incoming set.
        primaries: dict[ChannelType, int] = {}
        for i in v:
            if i.is_primary:
                primaries[i.channel_type] = primaries.get(i.channel_type, 0) + 1
        if any(c > 1 for c in primaries.values()):
            raise ValueError("at most one primary identifier per channel_type")
        return v


class PersonUpdate(BaseModel):
    """Partial update of identity fields. Identifiers/lead/customer/assignment are
    managed via their own endpoints, not here."""

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    birth_date: date_type | None = None
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    active: bool | None = None


class PersonPrimaryIdentifier(BaseModel):
    """Compact shape for the denormalized primary identifier in the list row
    (espejo de types/crm.types.ts:PersonPrimaryIdentifier)."""

    model_config = ConfigDict(from_attributes=True)
    channel_type: ChannelType
    identifier: str
    verified: bool


class LeadStatusSummary(BaseModel):
    """Compact lead status for badges (espejo de
    types/crm.types.ts:LeadStatusSummary). En F1 siempre None (sin tabla fuente)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_final: bool = False
    is_won: bool = False


class CustomerStatusSummary(BaseModel):
    """Compact customer status for badges (espejo de
    types/crm.types.ts:CustomerStatusSummary; sin is_won). En F1 siempre None."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    color: str | None = None
    is_final: bool = False


class PersonItem(BaseModel):
    """Row of the persons table. Denormalizes the primary identifier, the current
    lead/customer status summaries, the assigned advisor and last_activity_at so
    the list never needs the front to join. These are NOT columns of `person` →
    they are NOT in ALLOWED_FIELDS (lesson cd10c78): client-side search by
    name/handle, deep-link filters by *_id translated to EXISTS in the repo.

    ⚠ F1: lead_status/customer_status/assigned_advisor/last_activity_at son
    SIEMPRE None (no hay tabla fuente hasta F3/F4)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str  # f"{first_name} {last_name} {second_last_name or ''}".strip()
    first_name: str
    last_name: str
    second_last_name: str | None
    document_type: str | None
    document_number: str | None
    active: bool
    primary_identifier: PersonPrimaryIdentifier | None = None
    lead_status: LeadStatusSummary | None = None
    customer_status: CustomerStatusSummary | None = None
    assigned_advisor: UserAuditInfo | None = None
    last_activity_at: datetime | None = None
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class PersonDetail(PersonItem):
    """Full profile for the detail page. Adds the free-text/profile fields and the
    resolved identifiers collection (soft-deleted filtered out)."""

    birth_date: date_type | None
    gender: str | None
    address: str | None
    notes: str | None
    identifiers: list[ContactIdentifierItem]


class PersonOption(BaseModel):
    """Dropdown shape — GET /persons/active. Used by future modules (scheduling)
    and by /persons/search (the bot path)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    document_number: str | None = None
    primary_identifier: PersonPrimaryIdentifier | None = None
