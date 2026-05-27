"use client";

/**
 * Generic table query hook — wraps TanStack Query and URL state.
 *
 * - `page`, `pageSize`, `sort`, `filters` live in the URL via `nuqs`,
 *   so refresh / back-forward / share-link all work.
 * - The fetcher is a Server Action passed by the page.
 * - `revalidateTag` on the action side invalidates the cache and the
 *   hook refetches automatically.
 * - When the current request matches the server-prefetched default,
 *   `initialData` is used directly — no extra network round-trip on
 *   first render.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { parseAsInteger, parseAsString, useQueryStates } from "nuqs";

import { QueryParamsBuilder } from "@/lib/utils/query-builder";
import type { ApiPaginated } from "@/types/api.types";
import type { FilterCondition, SortOrder } from "@/types/query.types";

export interface UseTableQueryOptions<T> {
  queryKey: string;
  fetcher: (request: ReturnType<QueryParamsBuilder["build"]>) => Promise<ApiPaginated<T>>;
  /** Columns the URL `q` (search) parameter should match against. */
  searchFields?: string[];
  defaultSort?: { field: string; order: SortOrder };
  defaultPageSize?: number;
  /** Extra filter conditions injected on top of URL state. */
  extraFilters?: FilterCondition[];
  /**
   * Server-prefetched data for the default request. When the user hasn't
   * touched any filter / page / sort, this seeds the query cache with no
   * client-side fetch.
   */
  initialData?: ApiPaginated<T>;
  /** Mark `initialData` stale after this many ms (default: 30s). */
  staleTimeMs?: number;
}

export interface UseTableQueryReturn<T> {
  query: UseQueryResult<ApiPaginated<T>>;
  page: number;
  pageSize: number;
  setPage: (n: number) => void;
  setPageSize: (n: number) => void;
  search: string;
  setSearch: (s: string) => void;
  sortField: string;
  sortOrder: SortOrder;
  setSort: (field: string, order: SortOrder) => void;
}

export function useTableQuery<T>(opts: UseTableQueryOptions<T>): UseTableQueryReturn<T> {
  const defaultPageSize = opts.defaultPageSize ?? 10;
  const defaultSortField = opts.defaultSort?.field ?? "created_on";
  const defaultSortOrder: SortOrder = opts.defaultSort?.order ?? "desc";

  const [state, setState] = useQueryStates({
    page: parseAsInteger.withDefault(1),
    size: parseAsInteger.withDefault(defaultPageSize),
    q: parseAsString.withDefault(""),
    sort: parseAsString.withDefault(defaultSortField),
    dir: parseAsString.withDefault(defaultSortOrder),
  });

  const builder = new QueryParamsBuilder()
    .page(state.page, state.size)
    .sort(state.sort, state.dir as SortOrder);

  if (state.q && opts.searchFields?.length) {
    builder.whereOr(
      opts.searchFields.map((field) => ({ field, operator: "contains", value: state.q })),
    );
  }

  if (opts.extraFilters) {
    for (const c of opts.extraFilters) builder.where(c.field, c.operator, c.value);
  }

  const request = builder.build();

  // Use the server-prefetched payload only when the user hasn't deviated
  // from the default request. Otherwise, the prefetch is stale for this key.
  const isDefaultQuery =
    state.page === 1 &&
    state.size === defaultPageSize &&
    state.q === "" &&
    state.sort === defaultSortField &&
    state.dir === defaultSortOrder &&
    !opts.extraFilters?.length;

  const query = useQuery({
    queryKey: [opts.queryKey, request],
    queryFn: () => opts.fetcher(request),
    initialData: isDefaultQuery ? opts.initialData : undefined,
    staleTime: opts.staleTimeMs ?? 30_000,
    placeholderData: (prev) => prev,
  });

  return {
    query,
    page: state.page,
    pageSize: state.size,
    setPage: (n) => setState({ page: n }),
    setPageSize: (n) => setState({ size: n, page: 1 }),
    search: state.q,
    setSearch: (q) => setState({ q, page: 1 }),
    sortField: state.sort,
    sortOrder: state.dir as SortOrder,
    setSort: (field, order) => setState({ sort: field, dir: order, page: 1 }),
  };
}
