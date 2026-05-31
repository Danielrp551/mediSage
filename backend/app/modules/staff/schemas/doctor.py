"""
Schemas Pydantic v2 de Doctor. Variantes:
- DoctorUserCreate / DoctorCreate: input de creación NESTED (user + doctor).
- DoctorUpdate: actualización parcial del perfil + M:N (sin tocar la identidad
  del User, que se edita en el módulo admin, ni el user_id inmutable).
- DoctorItem: fila paginada, con full_name/email denormalizados del User +
  conteos batch de sedes/verticales.
- DoctorDetail: Item + bio/foto/firma + el User (audit shape) + los M:N resueltos.
- DoctorOption: dropdowns / selects.
- DoctorCreatedResponse: respuesta del POST (espeja admin.UserCreatedResponse).

Sin Ellipsis (`...`). Mensajes de validator en inglés (van al detalle 422); el
texto user-facing en español vive en el Zod del frontend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.catalog.schemas.vertical import VerticalOption
from app.modules.clinic.schemas.branch import BranchOption


class DoctorUserCreate(BaseModel):
    """Payload anidado del User para DoctorCreate. Espejo de admin.UserCreate
    menos role_ids/permission_ids — el service fuerza el rol DOCTOR. `password`
    es opcional: si falta, el service genera uno fuerte y lo devuelve una vez
    (mismo contrato que admin.user.create / UserCreatedResponse)."""

    email: EmailStr
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class DoctorCreate(BaseModel):
    """Creación NESTED: crea el User (asignando el rol DOCTOR) Y el Doctor en una
    sola transacción. Sin `user_id` — el user nace aquí."""

    user: DoctorUserCreate
    cmp_code: str | None = Field(default=None, max_length=40)
    bio: str | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    slot_duration_min: int = Field(default=30, ge=5, le=240)
    branch_ids: list[str] = Field(default_factory=list)
    vertical_ids: list[str] = Field(default_factory=list)

    @field_validator("branch_ids", "vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("ids must not contain duplicates")
        return v


class DoctorUpdate(BaseModel):
    """Actualización parcial del perfil profesional + M:N. NO actualizable:
    `user_id` (1:1 inmutable) y la identidad del User (email/nombre viven en el
    módulo admin). branch_ids/vertical_ids presentes = reemplazo total del M:N;
    ausentes = sin tocar."""

    cmp_code: str | None = Field(default=None, max_length=40)
    bio: str | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    slot_duration_min: int | None = Field(default=None, ge=5, le=240)
    branch_ids: list[str] | None = None
    vertical_ids: list[str] | None = None
    active: bool | None = None

    @field_validator("branch_ids", "vertical_ids")
    @classmethod
    def _no_dupes(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("ids must not contain duplicates")
        return v


class DoctorSelfUpdate(BaseModel):
    """Subset de DoctorUpdate que el doctor logueado puede editar de SU perfil
    vía PUT /me/doctor: solo campos profesionales propios. NO incluye branch_ids/
    vertical_ids (asignar sedes/verticales es decisión del admin) ni active
    (habilitar/deshabilitar también es del admin) ni la identidad del User."""

    cmp_code: str | None = Field(default=None, max_length=40)
    bio: str | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    slot_duration_min: int | None = Field(default=None, ge=5, le=240)


class DoctorItem(BaseModel):
    """Fila de la tabla de doctores. Denormaliza full_name/email del User (la
    lista nunca necesita un join) + conteos batch de sedes/verticales (mismo
    patrón que clinic OfficeItem.verticals_count)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    full_name: str  # denormalizado del User
    email: EmailStr  # denormalizado del User
    cmp_code: str | None
    slot_duration_min: int
    active: bool
    branches_count: int
    verticals_count: int
    created_on: datetime
    created_by: str
    created_by_user: UserAuditInfo | None = None
    updated_on: datetime
    updated_by: str
    updated_by_user: UserAuditInfo | None = None


class DoctorDetail(DoctorItem):
    """Perfil completo para la página de detalle. Agrega los campos de texto/
    media, el User resuelto (audit shape) y los M:N resueltos (sedes/verticales
    soft-deleted filtradas)."""

    bio: str | None
    photo_url: str | None
    signature_url: str | None
    user: UserAuditInfo
    branches: list[BranchOption]
    verticals: list[VerticalOption]


class DoctorOption(BaseModel):
    """Forma de dropdown — usada por GET /doctors/active y por scheduling/crm."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    cmp_code: str | None = None


class DoctorCreatedResponse(BaseModel):
    """Devuelta por POST /doctors — `generated_password` se setea cuando el caller
    no proporcionó una y el service la generó (mismo contrato que
    admin.UserCreatedResponse)."""

    success: bool = True
    data: DoctorDetail
    generated_password: str | None = None
