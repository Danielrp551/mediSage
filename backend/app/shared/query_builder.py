"""
Translate `QueryRequest` (a JSON-friendly DTO) into a SQLAlchemy query.

Every callable accepts a whitelist of `allowed_fields` so a request body
can't reach arbitrary columns (e.g. `password_hash`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Select, and_, asc, desc, func, or_, select
from sqlalchemy.orm import InspectionAttr

from app.core.database import Base
from app.core.exceptions import BadRequestException
from app.shared.base_schemas import (
    FilterCondition,
    FilterOperator,
    FilterParams,
    GroupOperator,
    PaginationParams,
    SortingParams,
)

logger = logging.getLogger(__name__)


def _column(model: type[Base], field: str, allowed: set[str]) -> InspectionAttr:
    if field not in allowed:
        raise BadRequestException(f"Field '{field}' is not filterable")
    col = getattr(model, field, None)
    if col is None:
        raise BadRequestException(f"Field '{field}' does not exist")
    return col


def _coerce(column: InspectionAttr, value: Any) -> Any:
    """Postgres rejects type mismatches — convert ISO strings to tz-aware datetime
    for `DateTime(timezone=True)` columns. Naive inputs are assumed UTC."""
    if not isinstance(value, str):
        return value
    try:
        col_type = column.property.columns[0].type
    except (AttributeError, IndexError):
        return value
    if isinstance(col_type, DateTime):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            logger.warning("query.cast.failed value=%r", value)
    return value


def _condition(column: InspectionAttr, c: FilterCondition) -> Any:
    v = _coerce(column, c.value)
    match c.operator:
        case FilterOperator.EQ: return column == v
        case FilterOperator.NEQ: return column != v
        case FilterOperator.CONTAINS: return column.ilike(f"%{v}%")
        case FilterOperator.STARTS_WITH: return column.ilike(f"{v}%")
        case FilterOperator.GT: return column > v
        case FilterOperator.GTE: return column >= v
        case FilterOperator.LT: return column < v
        case FilterOperator.LTE: return column <= v


def _where_clauses(model: type[Base], params: FilterParams | None, allowed: set[str]) -> list[Any]:
    if not params or not params.filters:
        return []
    groups: list[Any] = []
    for group in params.filters:
        if not group.conditions:
            continue
        clauses = [_condition(_column(model, c.field, allowed), c) for c in group.conditions]
        groups.append(and_(*clauses) if group.operator == GroupOperator.AND else or_(*clauses))
    return groups


def apply_filters(query: Select, model: type[Base], params: FilterParams | None, allowed: set[str]) -> Select:
    groups = _where_clauses(model, params, allowed)
    if groups:
        query = query.where(and_(*groups))
    return query


def apply_sorting(query: Select, model: type[Base], sorting: SortingParams | None, allowed: set[str]) -> Select:
    if not sorting:
        return query.order_by(asc(model.id))
    col = _column(model, sorting.sort_by, allowed)
    return query.order_by(desc(col) if sorting.sort_order.value == "desc" else asc(col))


def apply_pagination(query: Select, p: PaginationParams) -> Select:
    return query.offset(p.skip).limit(p.limit)


def build_count_query(model: type[Base], params: FilterParams | None, allowed: set[str]) -> Select:
    q = select(func.count(model.id))
    groups = _where_clauses(model, params, allowed)
    if groups:
        q = q.where(and_(*groups))
    return q
