"""
Cross-module Pydantic schemas: response envelopes + dynamic query request.

The frontend builds `QueryRequest` payloads via `QueryParamsBuilder`; the
backend's `BaseRepository.get_paginated` consumes them. Keep both ends
aligned when adding new operators.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# Datetimes round-trip naturally:
#   • DB columns are `timestamptz` → SQLAlchemy returns tz-aware datetimes.
#   • Pydantic v2 serialises tz-aware datetimes as ISO 8601 with offset
#     (e.g. `2026-05-26T10:11:12+00:00`), which JavaScript `new Date()`
#     parses identically to a trailing `Z`.
# No custom serialiser, no manual `Z`, no `.replace(tzinfo=None)`.


# ── Response envelopes ────────────────────────────

DataT = TypeVar("DataT")


class MessageResponse(BaseModel):
    success: bool = True
    detail: str


class SingleResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT


class PaginatedData(BaseModel, Generic[DataT]):
    items: list[DataT]
    total: int
    skip: int
    limit: int


class PaginatedResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: PaginatedData[DataT]


# ── Dynamic query request ─────────────────────────


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class FilterOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class GroupOperator(StrEnum):
    AND = "AND"
    OR = "OR"


class PaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=100)


class SortingParams(BaseModel):
    sort_by: str = Field(..., min_length=1)
    sort_order: SortOrder = SortOrder.ASC


class FilterCondition(BaseModel):
    field: str = Field(..., min_length=1)
    operator: FilterOperator
    value: Any


class FilterGroup(BaseModel):
    operator: GroupOperator = GroupOperator.AND
    conditions: list[FilterCondition] = Field(default_factory=list)


class FilterParams(BaseModel):
    filters: list[FilterGroup] = Field(default_factory=list)


class QueryRequest(BaseModel):
    pagination: PaginationParams = Field(default_factory=PaginationParams)
    sorting: SortingParams | None = None
    filters: FilterParams | None = None
