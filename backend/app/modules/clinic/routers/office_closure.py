"""
OfficeClosure endpoints, nested under /offices/{office_id}/closures. Individual
CRUD: GET (range-filterable) + POST + DELETE — no PUT (to fix a closure, delete
and recreate). Permission gating via `dependencies=[...]`.

`from` is a Python reserved word, so the query param is declared `from_` with an
alias so the URL keeps `?from=`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.clinic.schemas.office_closure import (
    OfficeClosureCreate,
    OfficeClosureDetail,
    OfficeClosureItem,
)
from app.modules.clinic.services import office_closure as closure_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/offices", tags=["clinic · office closures"])


OfficeIdPath = Annotated[str, Path(min_length=1, description="Office UUID")]
ClosureIdPath = Annotated[str, Path(min_length=1, description="Closure UUID")]


@router.get(
    "/{office_id}/closures",
    response_model=SingleResponse[list[OfficeClosureItem]],
    dependencies=[Depends(RequirePermission("OFFICE_CLOSURES_READ"))],
)
async def list_closures(
    office_id: OfficeIdPath,
    db: DBSession,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> SingleResponse[list[OfficeClosureItem]]:
    return await closure_service.list_for_office(db, office_id, from_, to)


@router.post(
    "/{office_id}/closures",
    response_model=SingleResponse[OfficeClosureDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("OFFICE_CLOSURES_WRITE"))],
)
async def create_closure(
    office_id: OfficeIdPath,
    payload: OfficeClosureCreate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[OfficeClosureDetail]:
    return await closure_service.create(db, office_id, payload, actor_id=actor.id)


@router.delete(
    "/{office_id}/closures/{closure_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("OFFICE_CLOSURES_WRITE"))],
)
async def delete_closure(
    office_id: OfficeIdPath,
    closure_id: ClosureIdPath,
    db: DBSession,
    actor: CurrentAuth,
) -> None:
    await closure_service.soft_delete(db, office_id, closure_id, actor_id=actor.id)
