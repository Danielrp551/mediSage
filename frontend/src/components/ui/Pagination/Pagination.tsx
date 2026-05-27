"use client";

import {
  Button,
  Dropdown,
  Option,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  ChevronDoubleLeftRegular,
  ChevronDoubleRightRegular,
  ChevronLeftRegular,
  ChevronRightRegular,
} from "@fluentui/react-icons";

import { appTokens } from "@/lib/theme/brand";

export interface PaginationProps {
  currentPage: number;
  pageSize: number;
  totalItems: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

const DEFAULT_OPTIONS = [10, 25, 50, 100];

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalL,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    borderTop: `1px solid ${appTokens.tableBorder}`,
    backgroundColor: appTokens.tableHeaderBg,
    flexWrap: "wrap",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  leftGroup: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
  },
  rightGroup: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  label: { whiteSpace: "nowrap" },
  pageSizeDropdown: {
    minWidth: "78px",
    width: "78px",
  },
  // Tabular numerals so the range text doesn't jitter when the digits change.
  range: {
    fontVariantNumeric: "tabular-nums",
    fontFeatureSettings: "'tnum'",
    color: appTokens.chromeText,
    fontWeight: tokens.fontWeightMedium,
    whiteSpace: "nowrap",
  },
  pageIndicator: {
    fontVariantNumeric: "tabular-nums",
    fontFeatureSettings: "'tnum'",
    minWidth: "70px",
    textAlign: "center",
    color: appTokens.chromeText,
    fontWeight: tokens.fontWeightMedium,
  },
  navButton: {
    minWidth: "32px",
    width: "32px",
    height: "32px",
    padding: 0,
  },
});

export function Pagination(props: PaginationProps) {
  const styles = useStyles();
  const totalPages = Math.max(1, Math.ceil(props.totalItems / props.pageSize));
  const from = props.totalItems === 0 ? 0 : (props.currentPage - 1) * props.pageSize + 1;
  const to = Math.min(props.totalItems, props.currentPage * props.pageSize);
  const isFirst = props.currentPage <= 1;
  const isLast = props.currentPage >= totalPages;
  const options = props.pageSizeOptions ?? DEFAULT_OPTIONS;

  return (
    <nav className={styles.root} aria-label="Pagination">
      <div className={styles.leftGroup}>
        <span className={styles.label}>Rows per page:</span>
        <Dropdown
          className={styles.pageSizeDropdown}
          value={String(props.pageSize)}
          selectedOptions={[String(props.pageSize)]}
          onOptionSelect={(_, data) =>
            props.onPageSizeChange(Number(data.optionValue))
          }
          size="small"
          aria-label="Rows per page"
        >
          {options.map((n) => (
            <Option key={n} value={String(n)}>
              {String(n)}
            </Option>
          ))}
        </Dropdown>
      </div>

      <div className={styles.rightGroup}>
        <span className={styles.range}>
          {from.toLocaleString()}–{to.toLocaleString()} of {props.totalItems.toLocaleString()}
        </span>

        <Button
          className={styles.navButton}
          appearance="subtle"
          icon={<ChevronDoubleLeftRegular />}
          aria-label="First page"
          disabled={isFirst}
          onClick={() => props.onPageChange(1)}
        />
        <Button
          className={styles.navButton}
          appearance="subtle"
          icon={<ChevronLeftRegular />}
          aria-label="Previous page"
          disabled={isFirst}
          onClick={() => props.onPageChange(props.currentPage - 1)}
        />

        <span className={styles.pageIndicator} aria-live="polite">
          Page {props.currentPage} / {totalPages}
        </span>

        <Button
          className={styles.navButton}
          appearance="subtle"
          icon={<ChevronRightRegular />}
          aria-label="Next page"
          disabled={isLast}
          onClick={() => props.onPageChange(props.currentPage + 1)}
        />
        <Button
          className={styles.navButton}
          appearance="subtle"
          icon={<ChevronDoubleRightRegular />}
          aria-label="Last page"
          disabled={isLast}
          onClick={() => props.onPageChange(totalPages)}
        />
      </div>
    </nav>
  );
}
