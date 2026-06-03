"""
ChannelAccount service. Módulo de funciones (no clases), per template convention.
CRUD estándar (molde `catalog.vertical`): `list_paginated`, `create` (guard
unicidad → 409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN), `get_by_id`, `update`,
`soft_delete`, `list_active`. Hidrata audit users (`created_by_user`/
`updated_by_user`) por batch lookup (sin N+1), igual que `catalog.vertical`.

El SECRETO nunca viaja a un schema: `_to_item` deriva `credentials_configured`/
`has_verify_token` de la presencia de `secret_name`/`webhook_verify_token` (jamás
el valor). El helper **server-only** `get_credentials(ca)` es el ÚNICO camino al
valor real (delega en `app.core.secrets` / fallback env, ADR-010).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    AlreadyExistsException,
    BadRequestException,
    NotFoundException,
)
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.conversations.models.channel_account import ChannelAccount
from app.modules.conversations.repositories.channel_account import channel_account_repository
from app.modules.conversations.schemas.channel_account import (
    ChannelAccountCreate,
    ChannelAccountDetail,
    ChannelAccountItem,
    ChannelAccountOption,
    ChannelAccountUpdate,
)
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import generate_uuid, utc_now


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _to_item(ca: ChannelAccount, audit_users: dict[str, User]) -> ChannelAccountItem:
    return ChannelAccountItem(
        id=ca.id,
        channel_type=ca.channel_type,
        name=ca.name,
        external_identifier=ca.external_identifier,
        phone_number_id=ca.phone_number_id,
        credentials_configured=ca.secret_name is not None,
        has_verify_token=ca.webhook_verify_token is not None,
        active=ca.active,
        created_on=ca.created_on,
        created_by=ca.created_by,
        created_by_user=_audit_info(audit_users.get(ca.created_by)),
        updated_on=ca.updated_on,
        updated_by=ca.updated_by,
        updated_by_user=_audit_info(audit_users.get(ca.updated_by)),
    )


def _to_detail(ca: ChannelAccount, audit_users: dict[str, User]) -> ChannelAccountDetail:
    return ChannelAccountDetail(
        **_to_item(ca, audit_users).model_dump(),
        secret_name=ca.secret_name,
        webhook_verify_token=ca.webhook_verify_token,
        bot_configuration_id=ca.bot_configuration_id,
        default_campaign_id=ca.default_campaign_id,
    )


def _collect_actor_ids(rows: list[ChannelAccount]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


async def list_active(db: AsyncSession) -> list[ChannelAccountOption]:
    """Cuentas activas para dropdowns. Devuelve la lista cruda (sin envelope),
    consistente con `catalog.vertical.list_active`."""
    rows = await channel_account_repository.list_active(db)
    return [ChannelAccountOption.model_validate(r, from_attributes=True) for r in rows]


async def get_by_id(
    db: AsyncSession, channel_account_id: str
) -> SingleResponse[ChannelAccountDetail]:
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")
    audit_users = await user_repository.get_audit_info_map(db, {ca.created_by, ca.updated_by})
    return SingleResponse(data=_to_detail(ca, audit_users))


async def list_paginated(
    db: AsyncSession, query_request: QueryRequest
) -> PaginatedResponse[ChannelAccountItem]:
    items, total = await channel_account_repository.get_paginated(db, query_request)
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(ca, audit_users) for ca in items],
            total=total,
            skip=query_request.pagination.skip,
            limit=query_request.pagination.limit,
        )
    )


async def create(
    db: AsyncSession, payload: ChannelAccountCreate, *, actor_id: str
) -> SingleResponse[ChannelAccountDetail]:
    existing = await channel_account_repository.get_by_external_id(
        db, payload.channel_type.value, payload.external_identifier
    )
    if existing is not None:
        raise AlreadyExistsException(
            f"Ya existe una cuenta de canal '{payload.channel_type.value}' con el "
            f"identificador '{payload.external_identifier}'",
            code="CHANNEL_ACCOUNT_EXTERNAL_TAKEN",
        )

    now = utc_now()
    ca = ChannelAccount(
        id=generate_uuid(),
        channel_type=payload.channel_type.value,
        name=payload.name,
        external_identifier=payload.external_identifier,
        secret_name=payload.secret_name,
        webhook_verify_token=payload.webhook_verify_token,
        phone_number_id=payload.phone_number_id,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
    )
    await channel_account_repository.create(db, ca)
    audit_users = await user_repository.get_audit_info_map(db, {ca.created_by, ca.updated_by})
    return SingleResponse(data=_to_detail(ca, audit_users))


async def update(
    db: AsyncSession,
    channel_account_id: str,
    payload: ChannelAccountUpdate,
    *,
    actor_id: str,
) -> SingleResponse[ChannelAccountDetail]:
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")

    changes = payload.model_dump(exclude_unset=True)
    # Un null EXPLÍCITO en un campo NOT NULL (name/external_identifier) es válido-por-tipo
    # en el Update parcial pero blanquearía la columna (IntegrityError/500) → se descarta
    # (None = "no cambiar"). `channel_type` es INMUTABLE (no está en el schema Update).
    for required in ("name", "external_identifier"):
        if required in changes and changes[required] is None:
            changes.pop(required)
    # `external_identifier` editable → re-dispara el guard de unicidad sobre el par vivo
    # (channel_type [inmutable, el de la fila], external_identifier).
    if "external_identifier" in changes:
        clash = await channel_account_repository.get_by_external_id(
            db, ca.channel_type, changes["external_identifier"]
        )
        if clash is not None and clash.id != ca.id:
            raise AlreadyExistsException(
                f"Ya existe una cuenta de canal '{ca.channel_type}' con el "
                f"identificador '{changes['external_identifier']}'",
                code="CHANNEL_ACCOUNT_EXTERNAL_TAKEN",
            )

    changes["updated_by"] = actor_id
    changes["updated_on"] = utc_now()

    await channel_account_repository.update(db, ca, changes)
    audit_users = await user_repository.get_audit_info_map(db, {ca.created_by, ca.updated_by})
    return SingleResponse(data=_to_detail(ca, audit_users))


async def soft_delete(db: AsyncSession, channel_account_id: str, *, actor_id: str) -> None:
    ca = await channel_account_repository.get_by_id(db, channel_account_id)
    if ca is None:
        raise NotFoundException("Cuenta de canal no encontrada", code="CHANNEL_ACCOUNT_NOT_FOUND")
    ca.updated_by = actor_id
    ca.updated_on = utc_now()
    await channel_account_repository.soft_delete(db, ca)


async def get_credentials(db: AsyncSession, ca: ChannelAccount) -> dict[str, str]:
    """SERVER-ONLY. Resuelve las credenciales del canal para firmar/verificar/enviar.
    Si `ca.secret_name` está set y no estamos en dev → `secrets.resolve(ca.secret_name)`
    (Secret Manager, cacheado). Si NULL, o `ENV_NAME=dev`, o `USE_LOCAL_SECRETS` →
    fallback a env (`Settings.WHATSAPP_*`). Vacío/404 → CHANNEL_CREDENTIALS_MISSING.
    NUNCA se expone por la API. `db` se mantiene en la firma por consistencia con los
    callers (webhook/outbound) aunque no se use directamente acá."""
    from app.core import secrets

    settings = get_settings()
    use_local = settings.ENV_NAME == "dev" or settings.USE_LOCAL_SECRETS
    if ca.secret_name and not use_local:
        creds = await secrets.resolve(ca.secret_name)
    else:
        creds = {
            "access_token": settings.WHATSAPP_ACCESS_TOKEN,
            "app_secret": settings.WHATSAPP_APP_SECRET,
            "phone_number_id": ca.phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID,
        }
    if not creds or not creds.get("access_token") or not creds.get("app_secret"):
        raise BadRequestException(
            "Faltan las credenciales del canal (Secret Manager / env)",
            code="CHANNEL_CREDENTIALS_MISSING",
        )
    return creds
