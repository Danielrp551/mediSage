/**
 * Fluent builder for the backend's `QueryRequest`.
 *
 * Example:
 *   const payload = new QueryParamsBuilder()
 *     .page(2, 25)
 *     .sort("created_on", "desc")
 *     .where("active", "eq", true)
 *     .whereOr([{ field: "first_name", operator: "contains", value: "a" }])
 *     .build();
 */

import type {
  FilterCondition,
  FilterOperator,
  QueryRequest,
  SortOrder,
} from "@/types/query.types";

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

export class QueryParamsBuilder {
  private skip = 0;
  private limit = 10;
  private sortBy: string | null = null;
  private sortDir: SortOrder = "asc";
  private andConds: FilterCondition[] = [];
  private orConds: FilterCondition[] = [];

  page(page: number, pageSize: number): this {
    this.skip = Math.max(0, (page - 1) * pageSize);
    this.limit = pageSize;
    return this;
  }

  sort(field: string, order: SortOrder = "asc"): this {
    this.sortBy = field;
    this.sortDir = order;
    return this;
  }

  where(field: string, operator: FilterOperator, value: unknown): this {
    if (!isEmpty(value)) {
      this.andConds.push({ field, operator, value });
    }
    return this;
  }

  whereOr(conditions: FilterCondition[]): this {
    for (const c of conditions) {
      if (!isEmpty(c.value)) this.orConds.push(c);
    }
    return this;
  }

  build(): QueryRequest {
    const filterGroups = [];
    if (this.andConds.length) filterGroups.push({ operator: "AND" as const, conditions: this.andConds });
    if (this.orConds.length) filterGroups.push({ operator: "OR" as const, conditions: this.orConds });

    return {
      pagination: { skip: this.skip, limit: this.limit },
      sorting: this.sortBy ? { sort_by: this.sortBy, sort_order: this.sortDir } : null,
      filters: filterGroups.length ? { filters: filterGroups } : null,
    };
  }
}
