"use client";

/**
 * Generic data table — wraps Fluent UI primitives but adds the patterns
 * we want everywhere: ergonomic empty state (with a "no results" variant
 * for when the user has filtered), skeleton loader, hover rows, column
 * alignment, tabular numerals for numeric columns, truncate + tooltip,
 * and a polished pagination strip.
 *
 * All visual values come from `appTokens` / `tokens.*` — change the
 * palette / typography in `lib/theme/brand.ts` and the table follows.
 */

import {
  Skeleton,
  SkeletonItem,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Tooltip,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import { DocumentDismissRegular, SearchRegular } from "@fluentui/react-icons";
import type { ReactNode } from "react";

import { appTokens } from "@/lib/theme/brand";
import { Pagination } from "../Pagination/Pagination";

// ── Public types ──────────────────────────────────

export type ColumnAlign = "left" | "center" | "right";

export interface DataTableColumn<T> {
  key: string;
  name: string;
  /** Direct value access (used when `onRender` isn't provided). */
  fieldName?: keyof T;
  minWidth?: number;
  maxWidth?: number;
  isSortable?: boolean;
  /** Truncate overflowing text + show full value in a tooltip on hover. */
  truncate?: boolean;
  /** Cell + header alignment. Defaults to `left` (or `right` if `numeric`). */
  align?: ColumnAlign;
  /** Right-align + tabular numerals (digits line up vertically). */
  numeric?: boolean;
  /** Custom cell renderer. Receives the row and its index. */
  onRender?: (item: T, idx: number) => ReactNode;
}

export interface DataTableProps<T> {
  items: T[];
  columns: DataTableColumn<T>[];
  getRowKey: (item: T, idx: number) => string;
  /** Initial load = no items yet; show skeleton rows. */
  isLoading?: boolean;
  /** Background refetch — keep old data visible, dim it. */
  isFetching?: boolean;
  /** A search/filter is active (drives the empty-state variant). */
  isFiltered?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
  onRowClick?: (item: T) => void;
  onSort?: (key: string, descending: boolean) => void;
  sortField?: string;
  sortOrder?: "asc" | "desc";
  /** Optional zebra striping. Off by default — keeps the table calmer. */
  striped?: boolean;
  pagination?: {
    page: number;
    pageSize: number;
    total: number;
    onPageChange: (p: number) => void;
    onPageSizeChange: (s: number) => void;
  };
}

// ── Styles ────────────────────────────────────────

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    backgroundColor: appTokens.contentBg,
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    overflow: "hidden",
    boxShadow: tokens.shadow2,
  },
  scroll: {
    overflowX: "auto",
    overflowY: "visible",
    // Custom scrollbar so the table feels polished on Windows / Chromium.
    "&::-webkit-scrollbar": { height: "10px" },
    "&::-webkit-scrollbar-track": { backgroundColor: appTokens.contentBg },
    "&::-webkit-scrollbar-thumb": {
      backgroundColor: appTokens.tableBorder,
      borderRadius: "5px",
    },
    "&::-webkit-scrollbar-thumb:hover": { backgroundColor: appTokens.chromeBgHover },
  },
  fade: {
    opacity: 0.55,
    pointerEvents: "none",
    transition: "opacity 120ms ease",
  },
  table: { width: "100%" },
  headerRow: { backgroundColor: appTokens.tableHeaderBg },
  headerCell: {
    color: appTokens.tableHeaderText,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    whiteSpace: "nowrap",
    borderBottom: `1px solid ${appTokens.tableBorder}`,
    paddingTop: tokens.spacingVerticalS,
    paddingBottom: tokens.spacingVerticalS,
  },
  headerSortable: {
    cursor: "pointer",
    userSelect: "none",
    "&:hover": { color: appTokens.chromeText, backgroundColor: appTokens.tableRowHover },
  },
  // Fluent v9 cells use flex internally; `text-align` alone won't reposition
  // flex children (e.g. a Badge). Use `justify-content` for the flex axis
  // and keep `text-align` for inline text fallback.
  alignCenter: { textAlign: "center", justifyContent: "center" },
  alignRight: { textAlign: "right", justifyContent: "flex-end" },
  bodyCell: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    borderBottom: `1px solid ${appTokens.tableBorder}`,
    paddingTop: tokens.spacingVerticalSNudge,
    paddingBottom: tokens.spacingVerticalSNudge,
    // Grid items default to `min-width: auto`, which keeps cells at content
    // size and prevents the inner ellipsis span from shrinking. `min-width: 0`
    // lets the cell honour the column's grid track width so truncate works.
    minWidth: 0,
  },
  bodyCellNumeric: {
    fontVariantNumeric: "tabular-nums",
    fontFeatureSettings: "'tnum'",
    textAlign: "right",
  },
  // Ellipsis wrapper — lives on the inner <span>, NOT on the <td>. Applying
  // these styles to the cell collapses it in Fluent v9's layout (the cell
  // shrinks to a 1px ellipsis dot — what looked like an empty column).
  truncateText: {
    display: "block",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  row: { transition: "background-color 100ms ease" },
  rowStriped: {
    "&:nth-of-type(even)": { backgroundColor: appTokens.tableRowStripe },
  },
  rowClickable: {
    cursor: "pointer",
    "&:hover": { backgroundColor: appTokens.tableRowHover },
  },
  rowLast: { "& > td": { borderBottom: "none" } },
  // Loading / Empty / NoResults shared container
  state: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    color: appTokens.chromeTextMuted,
    textAlign: "center",
    minHeight: "240px",
  },
  stateIcon: {
    fontSize: "40px",
    color: appTokens.chromeTextMuted,
    opacity: 0.7,
  },
  stateTitle: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  stateMessage: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
    maxWidth: "360px",
    lineHeight: 1.5,
  },
  // Overlay spinner for background refetches that DO have current data
  refetchOverlay: {
    position: "absolute",
    top: "8px",
    right: "8px",
    zIndex: 2,
    backgroundColor: appTokens.contentBg,
    borderRadius: tokens.borderRadiusCircular,
    padding: "4px",
    boxShadow: tokens.shadow4,
  },
  tableWrap: { position: "relative" },
  skeletonRow: {
    display: "grid",
    alignItems: "center",
    height: "44px",
    paddingLeft: tokens.spacingHorizontalM,
    paddingRight: tokens.spacingHorizontalM,
    borderBottom: `1px solid ${appTokens.tableBorder}`,
  },
});

// ── Helpers ───────────────────────────────────────

function resolveAlign<T>(col: DataTableColumn<T>): ColumnAlign {
  if (col.align) return col.align;
  if (col.numeric) return "right";
  return "left";
}

function alignClass(
  align: ColumnAlign,
  styles: { alignCenter: string; alignRight: string },
): string | undefined {
  if (align === "center") return styles.alignCenter;
  if (align === "right") return styles.alignRight;
  return undefined;
}

// ── Component ─────────────────────────────────────

export function DataTable<T>(props: DataTableProps<T>) {
  const styles = useStyles();
  const {
    items,
    columns,
    getRowKey,
    isLoading = false,
    isFetching = false,
    isFiltered = false,
    onRowClick,
    onSort,
    sortField,
    sortOrder,
    striped = false,
    pagination,
    emptyTitle,
    emptyMessage,
  } = props;

  const handleSort = (col: DataTableColumn<T>) => {
    if (!col.isSortable || !onSort) return;
    const isCurrent = sortField === col.key;
    const descending = isCurrent ? sortOrder !== "desc" : false;
    onSort(col.key, descending);
  };

  const hasNoData = !isLoading && items.length === 0;

  return (
    <div className={styles.card}>
      <div className={styles.tableWrap}>
        {/* Background refetch indicator — keeps data visible. */}
        {isFetching && !isLoading && items.length > 0 ? (
          <div className={styles.refetchOverlay}>
            <Spinner size="extra-small" aria-label="Refreshing" />
          </div>
        ) : null}

        <div className={styles.scroll}>
          <Table
            className={mergeClasses(
              styles.table,
              isFetching && !isLoading && items.length > 0 && styles.fade,
            )}
            sortable
          >
            <TableHeader>
              <TableRow className={styles.headerRow}>
                {columns.map((col) => {
                  const align = resolveAlign(col);
                  const isSorted = col.isSortable && sortField === col.key;
                  return (
                    <TableHeaderCell
                      key={col.key}
                      className={mergeClasses(
                        styles.headerCell,
                        col.isSortable && styles.headerSortable,
                        alignClass(align, styles),
                      )}
                      onClick={() => handleSort(col)}
                      sortable={col.isSortable}
                      sortDirection={
                        isSorted
                          ? sortOrder === "desc"
                            ? "descending"
                            : "ascending"
                          : undefined
                      }
                      style={{
                        minWidth: col.minWidth ?? 120,
                        maxWidth: col.maxWidth,
                      }}
                    >
                      {col.name}
                    </TableHeaderCell>
                  );
                })}
              </TableRow>
            </TableHeader>

            <TableBody>
              {isLoading ? (
                <SkeletonRows columns={columns} styles={styles} />
              ) : hasNoData ? (
                <TableRow>
                  <TableCell colSpan={columns.length} style={{ borderBottom: "none" }}>
                    {isFiltered ? (
                      <EmptyState
                        icon={<SearchRegular className={styles.stateIcon} />}
                        title="No results match your filters"
                        message="Try removing some criteria or check for typos in the search term."
                        styles={styles}
                      />
                    ) : (
                      <EmptyState
                        icon={<DocumentDismissRegular className={styles.stateIcon} />}
                        title={emptyTitle ?? "Nothing here yet"}
                        message={emptyMessage ?? "Items you create will show up in this list."}
                        styles={styles}
                      />
                    )}
                  </TableCell>
                </TableRow>
              ) : (
                items.map((item, idx) => (
                  <TableRow
                    key={getRowKey(item, idx)}
                    className={mergeClasses(
                      styles.row,
                      striped && styles.rowStriped,
                      onRowClick && styles.rowClickable,
                      idx === items.length - 1 && styles.rowLast,
                    )}
                    onClick={onRowClick ? () => onRowClick(item) : undefined}
                  >
                    {columns.map((col) => {
                      const align = resolveAlign(col);
                      const raw =
                        col.onRender !== undefined
                          ? col.onRender(item, idx)
                          : col.fieldName !== undefined
                            ? (item[col.fieldName] as ReactNode) ?? "—"
                            : null;

                      const content =
                        col.truncate && typeof raw === "string" ? (
                          <Tooltip content={raw} relationship="label" withArrow>
                            <span className={styles.truncateText}>{raw}</span>
                          </Tooltip>
                        ) : (
                          raw
                        );

                      return (
                        <TableCell
                          key={col.key}
                          className={mergeClasses(
                            styles.bodyCell,
                            col.numeric && styles.bodyCellNumeric,
                            alignClass(align, styles),
                          )}
                          style={{ maxWidth: col.maxWidth }}
                        >
                          {content}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {pagination && !isLoading && items.length > 0 ? (
        <Pagination
          currentPage={pagination.page}
          pageSize={pagination.pageSize}
          totalItems={pagination.total}
          onPageChange={pagination.onPageChange}
          onPageSizeChange={pagination.onPageSizeChange}
        />
      ) : null}
    </div>
  );
}

// ── Sub-components ────────────────────────────────

// Structural type — `SkeletonRows` only needs `key` from each column.
// Typing as `DataTableColumn<unknown>[]` doesn't work: `DataTableColumn<T>`
// is invariant in `T` (because `onRender(item: T)` is contravariant in `T`),
// so `DataTableColumn<MyRow>[]` is NOT assignable to `DataTableColumn<unknown>[]`
// without a cast. Asking only for `{ key: string }` sidesteps the issue.
function SkeletonRows({
  columns,
  styles,
}: {
  columns: ReadonlyArray<{ key: string }>;
  styles: ReturnType<typeof useStyles>;
}) {
  return (
    <>
      {Array.from({ length: 6 }).map((_, rowIdx) => (
        <TableRow key={`sk-${rowIdx}`}>
          {columns.map((col, colIdx) => (
            <TableCell key={col.key} className={styles.bodyCell}>
              <Skeleton>
                <SkeletonItem
                  shape="rectangle"
                  size={16}
                  style={{
                    width: `${60 + ((rowIdx * 13 + colIdx * 7) % 30)}%`,
                  }}
                />
              </Skeleton>
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  message: string;
  styles: ReturnType<typeof useStyles>;
}

function EmptyState({ icon, title, message, styles }: EmptyStateProps) {
  return (
    <div className={styles.state} role="status">
      {icon}
      <div className={styles.stateTitle}>{title}</div>
      <div className={styles.stateMessage}>{message}</div>
    </div>
  );
}
