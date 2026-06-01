"""
Endpoints anidados de PersonContactIdentifier bajo `/persons/{id}/identifiers`.
GET requiere `PERSONS_READ`; el resto (POST/PUT/DELETE) `PERSONS_UPDATE`. El
service verifica que la persona exista (404 PERSON_NOT_FOUND) y el ownership de
cada identifier (404 IDENTIFIER_NOT_FOUND).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.contact_identifier import (
    ContactIdentifierCreate,
    ContactIdentifierItem,
    ContactIdentifierUpdate,
)
from app.modules.crm.services import contact_identifier as identifier_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · identifiers"])


PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]
IdentifierIdPath = Annotated[str, Path(min_length=1, description="Identifier UUID")]


@router.get(
    "/{person_id}/identifiers",
    response_model=SingleResponse[list[ContactIdentifierItem]],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def list_identifiers(
    person_id: PersonIdPath, db: DBSession
) -> SingleResponse[list[ContactIdentifierItem]]:
    return await identifier_service.list_for_person(db, person_id)


@router.post(
    "/{person_id}/identifiers",
    response_model=SingleResponse[ContactIdentifierItem],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("PERSONS_UPDATE"))],
)
async def add_identifier(
    person_id: PersonIdPath,
    payload: ContactIdentifierCreate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ContactIdentifierItem]:
    return await identifier_service.add(db, person_id, payload, actor_id=actor.id)


@router.put(
    "/{person_id}/identifiers/{identifier_id}",
    response_model=SingleResponse[ContactIdentifierItem],
    dependencies=[Depends(RequirePermission("PERSONS_UPDATE"))],
)
async def update_identifier(
    person_id: PersonIdPath,
    identifier_id: IdentifierIdPath,
    payload: ContactIdentifierUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ContactIdentifierItem]:
    return await identifier_service.update(db, person_id, identifier_id, payload, actor_id=actor.id)


@router.delete(
    "/{person_id}/identifiers/{identifier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("PERSONS_UPDATE"))],
)
async def delete_identifier(
    person_id: PersonIdPath,
    identifier_id: IdentifierIdPath,
    db: DBSession,
    actor: CurrentAuth,
) -> None:
    await identifier_service.remove(db, person_id, identifier_id, actor_id=actor.id)
