"""
Service de conexiones (módulo de funciones, NO clases). list / get / disconnect +
list_external_calendars (live, para la UI de mapeo). Hidrata audit users (created_by_user/
updated_by_user) por batch (sin N+1) y denormaliza sources_count + branch_name.

`_resolve_creds` (lee el secreto → Credentials; refresca al vuelo si expiró + re-escribe el
secreto) vive acá porque `list_external_calendars` (F1a) lo necesita; F2 (`external_read`) lo
reusa. Excepciones de dominio (NUNCA HTTPException); actor_id explícito; reload-via-get_full.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import secrets
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.admin.models.user import User
from app.modules.admin.repositories.user import user_repository
from app.modules.admin.schemas.audit import UserAuditInfo
from app.modules.calendar.enums import ConnectionStatus
from app.modules.calendar.models.calendar_connection import CalendarConnection
from app.modules.calendar.models.calendar_source import CalendarSource
from app.modules.calendar.repositories.calendar_connection import (
    calendar_connection_repository,
)
from app.modules.calendar.repositories.calendar_source import (
    calendar_source_repository,
)
from app.modules.calendar.schemas.connection import (
    CalendarConnectionDetail,
    CalendarConnectionItem,
)
from app.modules.calendar.schemas.source import (
    CalendarSourceItem,
    ExternalCalendarOption,
)
from app.modules.calendar.services.providers import get_adapter
from app.modules.calendar.services.providers.base import Credentials, _CalendarAdapter
from app.modules.clinic.repositories.branch import branch_repository
from app.shared.base_schemas import (
    PaginatedData,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)
from app.shared.utils import utc_now

# ── Credenciales: (de)serialización + refresh al vuelo ──


def creds_from_payload(raw: dict[str, Any]) -> Credentials:
    """Rehidrata `Credentials` desde el JSON de Secret Manager (expiry ISO → datetime)."""
    return Credentials(
        access_token=raw["access_token"],
        refresh_token=raw.get("refresh_token"),
        expiry=datetime.fromisoformat(raw["expiry"]),
        scopes=list(raw.get("scopes") or []),
    )


def creds_payload(creds: Credentials) -> dict[str, Any]:
    """Serializa `Credentials` al JSON que vive en Secret Manager."""
    return {
        "access_token": creds.access_token,
        "refresh_token": creds.refresh_token,
        "expiry": creds.expiry.isoformat(),
        "scopes": creds.scopes,
    }


async def resolve_creds(
    db: AsyncSession, conn: CalendarConnection, adapter: _CalendarAdapter
) -> Credentials:
    """Lee el secreto → Credentials; si expiry <= now refresca y RE-ESCRIBE el secreto
    (secrets.put). `invalid_grant` → marca la conexión needs_reauth + CALENDAR_TOKEN_REFRESH_
    FAILED. Usado por la lectura de config (propaga el error) y por F2 (best-effort, atrapa)."""
    raw = await secrets.resolve(conn.secret_name)  # CALENDAR_CREDENTIALS_MISSING si falla
    creds = creds_from_payload(raw)
    if creds.expiry <= utc_now():
        try:
            creds = await adapter.refresh(creds)
        except Exception as exc:
            conn.status = ConnectionStatus.needs_reauth.value
            conn.last_error = "invalid_grant"
            raise BadRequestException(
                "No se pudo refrescar el token", code="CALENDAR_TOKEN_REFRESH_FAILED"
            ) from exc
        await secrets.put(conn.secret_name, creds_payload(creds))  # rota el access token
    return creds


# ── Mapeo modelo → schema ──


def _audit_info(actor: User | None) -> UserAuditInfo | None:
    if actor is None:
        return None
    return UserAuditInfo(id=actor.id, full_name=actor.full_name, email=actor.email)


def _collect_actor_ids(rows: list[CalendarConnection]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.add(row.created_by)
        ids.add(row.updated_by)
    return ids


def _to_item(
    conn: CalendarConnection,
    audit_users: dict[str, User],
    *,
    sources_count: int = 0,
) -> CalendarConnectionItem:
    return CalendarConnectionItem(
        id=conn.id,
        provider=conn.provider,
        account_email=conn.account_email,
        display_name=conn.display_name,
        status=conn.status,
        scopes=conn.scopes,
        last_checked_at=conn.last_checked_at,
        sources_count=sources_count,
        is_active=conn.active,
        created_on=conn.created_on,
        created_by=conn.created_by,
        created_by_user=_audit_info(audit_users.get(conn.created_by)),
        updated_on=conn.updated_on,
        updated_by=conn.updated_by,
        updated_by_user=_audit_info(audit_users.get(conn.updated_by)),
    )


def _source_to_item(source: CalendarSource, branch_names: dict[str, str]) -> CalendarSourceItem:
    return CalendarSourceItem(
        id=source.id,
        connection_id=source.connection_id,
        external_calendar_id=source.external_calendar_id,
        external_calendar_name=source.external_calendar_name,
        branch_id=source.branch_id,
        branch_name=branch_names.get(source.branch_id) if source.branch_id else None,
        is_enabled=source.active,
    )


def _to_detail(
    conn: CalendarConnection,
    audit_users: dict[str, User],
    branch_names: dict[str, str],
) -> CalendarConnectionDetail:
    base = _to_item(conn, audit_users, sources_count=len(conn.sources)).model_dump()
    return CalendarConnectionDetail(
        **base,
        last_error=conn.last_error,
        sources=[_source_to_item(s, branch_names) for s in conn.sources],
    )


async def _branch_name_map(db: AsyncSession, branch_ids: list[str]) -> dict[str, str]:
    """Denorm batch de branch_id → branch.name (clinic). Solo ids no-NULL."""
    ids = [bid for bid in branch_ids if bid]
    if not ids:
        return {}
    branches = await branch_repository.get_by_ids(db, list(set(ids)))
    return {b.id: b.name for b in branches}


# ── Endpoints de service ──


async def list_connections(
    db: AsyncSession, query: QueryRequest
) -> PaginatedResponse[CalendarConnectionItem]:
    items, total = await calendar_connection_repository.get_paginated(db, query)
    counts = await calendar_connection_repository.sources_count_map(db, [c.id for c in items])
    audit_users = await user_repository.get_audit_info_map(db, _collect_actor_ids(items))
    return PaginatedResponse(
        data=PaginatedData(
            items=[_to_item(c, audit_users, sources_count=counts.get(c.id, 0)) for c in items],
            total=total,
            skip=query.pagination.skip,
            limit=query.pagination.limit,
        )
    )


async def get_connection(
    db: AsyncSession, connection_id: str
) -> SingleResponse[CalendarConnectionDetail]:
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")
    branch_names = await _branch_name_map(db, [s.branch_id for s in conn.sources if s.branch_id])
    audit_users = await user_repository.get_audit_info_map(db, {conn.created_by, conn.updated_by})
    return SingleResponse(data=_to_detail(conn, audit_users, branch_names))


async def disconnect(db: AsyncSession, connection_id: str, *, actor_id: str) -> None:
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")
    # Best-effort: borrar el secreto (un secreto huérfano no es crítico; si falla no rompe el
    # disconnect). El revoke real en el provider es B-futuro (el token caduca solo).
    try:
        await secrets.put(conn.secret_name, {})  # invalida el contenido del secreto
    except Exception:  # noqa: BLE001 — best-effort: el disconnect no depende del secreto
        pass
    # Soft-delete los sources + la conexión (audit cols antes del soft_delete, molde branch).
    await calendar_source_repository.soft_delete_for_connection(db, connection_id)
    conn.updated_by = actor_id
    conn.updated_on = utc_now()
    await calendar_connection_repository.soft_delete(db, conn)


async def list_external_calendars(
    db: AsyncSession, connection_id: str
) -> SingleResponse[list[ExternalCalendarOption]]:
    """Live list_calendars (para la UI de mapeo). Refresca el token si expiró. Si el provider
    falla → CALENDAR_TOKEN_REFRESH_FAILED (la UI de config SÍ propaga el error, a diferencia
    del overlay F2 que es best-effort)."""
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")
    adapter = get_adapter(conn.provider)
    creds = await resolve_creds(db, conn, adapter)
    calendars = await adapter.list_calendars(creds)
    return SingleResponse(
        data=[ExternalCalendarOption(id=c.id, name=c.name, primary=c.primary) for c in calendars]
    )
