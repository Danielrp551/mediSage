// QueryRequest types — mirrors app/shared/base_schemas.py:QueryRequest on the backend.

export type FilterOperator =
  | "eq"
  | "neq"
  | "contains"
  | "starts_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte";

export type GroupOperator = "AND" | "OR";

export type SortOrder = "asc" | "desc";

export interface FilterCondition {
  field: string;
  operator: FilterOperator;
  value: unknown;
}

export interface FilterGroup {
  operator: GroupOperator;
  conditions: FilterCondition[];
}

export interface FilterParams {
  filters: FilterGroup[];
}

export interface PaginationParams {
  skip: number;
  limit: number;
}

export interface SortingParams {
  sort_by: string;
  sort_order: SortOrder;
}

export interface QueryRequest {
  pagination: PaginationParams;
  sorting?: SortingParams | null;
  filters?: FilterParams | null;
}
