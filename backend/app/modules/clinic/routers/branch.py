"""
Branch CRUD endpoints. Permission gating via `dependencies=[...]` at the
decorator (per fastapi skill + template convention). `actor: CurrentAuth` is
requested separately when the handler needs the user id for audit columns.

`/active` is declared before `/{branch_id}` so the literal path isn't captured
by the id route. `/list` is POST + body (`QueryRequest`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.clinic.schemas.branch import (
    BranchCreate,
    BranchDetail,
    BranchItem,
    BranchOption,
    BranchUpdate,
)
from app.modules.clinic.services import branch as branch_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/branches", tags=["clinic · branches"])


BranchIdPath = Annotated[str, Path(min_length=1, description="Branch UUID")]


@router.get(
    "/active",
    response_model=list[BranchOption],
    dependencies=[Depends(RequirePermission("BRANCHES_READ"))],
)
async def list_active_branches(db: DBSession) -> list[BranchOption]:
    return await branch_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[BranchItem],
    dependencies=[Depends(RequirePermission("BRANCHES_READ"))],
)
async def list_branches(query: QueryRequest, db: DBSession) -> PaginatedResponse[BranchItem]:
    return await branch_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[BranchDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("BRANCHES_CREATE"))],
)
async def create_branch(
    payload: BranchCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[BranchDetail]:
    return await branch_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{branch_id}",
    response_model=SingleResponse[BranchDetail],
    dependencies=[Depends(RequirePermission("BRANCHES_READ"))],
)
async def get_branch(branch_id: BranchIdPath, db: DBSession) -> SingleResponse[BranchDetail]:
    return await branch_service.get_by_id(db, branch_id)


@router.put(
    "/{branch_id}",
    response_model=SingleResponse[BranchDetail],
    dependencies=[Depends(RequirePermission("BRANCHES_UPDATE"))],
)
async def update_branch(
    branch_id: BranchIdPath,
    payload: BranchUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[BranchDetail]:
    return await branch_service.update(db, branch_id, payload, actor_id=actor.id)


@router.delete(
    "/{branch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("BRANCHES_DELETE"))],
)
async def delete_branch(branch_id: BranchIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await branch_service.soft_delete(db, branch_id, actor_id=actor.id)
