"use client";

import { Checkbox, Input, makeStyles, tokens } from "@fluentui/react-components";
import { SearchRegular } from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { appTokens } from "@/lib/theme/brand";

/**
 * Generic searchable, multi-select checklist. Extracted from UserDrawer so the
 * roles/permissions pickers AND the office↔vertical picker share one helper
 * (zero duplicated logic). Self-contained styling — callers just pass options +
 * the controlled `selected` array and an `onToggle` handler.
 */

export interface OptionItem {
  id: string;
  primary: string;
  secondary?: string;
}

const useStyles = makeStyles({
  searchRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    marginBottom: tokens.spacingVerticalS,
  },
  searchInput: { flex: 1 },
  optionList: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    maxHeight: "320px",
    overflowY: "auto",
    paddingRight: tokens.spacingHorizontalXS,
  },
  optionRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusMedium,
    cursor: "pointer",
    "&:hover": { backgroundColor: appTokens.chromeBgHover },
  },
  optionRowDisabled: {
    cursor: "default",
    opacity: 0.6,
    "&:hover": { backgroundColor: "transparent" },
  },
  optionBody: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    flex: 1,
    minWidth: 0,
  },
  optionTitle: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    fontWeight: tokens.fontWeightSemibold,
  },
  optionSubtle: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  emptyState: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    padding: tokens.spacingVerticalM,
    textAlign: "center",
  },
});

interface Props {
  options: OptionItem[];
  selected: string[];
  disabled: boolean;
  onToggle: (id: string) => void;
  searchPlaceholder: string;
  emptyMessage: string;
}

export function SearchableOptionList({
  options,
  selected,
  disabled,
  onToggle,
  searchPlaceholder,
  emptyMessage,
}: Props) {
  const styles = useStyles();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) =>
        o.primary.toLowerCase().includes(q) ||
        (o.secondary && o.secondary.toLowerCase().includes(q)),
    );
  }, [options, query]);

  return (
    <>
      <div className={styles.searchRow}>
        <Input
          className={styles.searchInput}
          value={query}
          onChange={(_, d) => setQuery(d.value)}
          placeholder={searchPlaceholder}
          contentBefore={<SearchRegular />}
          size="small"
        />
      </div>
      <div className={styles.optionList}>
        {filtered.length === 0 ? (
          <div className={styles.emptyState}>{emptyMessage}</div>
        ) : (
          filtered.map((opt) => {
            const checked = selected.includes(opt.id);
            return (
              <label
                key={opt.id}
                className={`${styles.optionRow} ${disabled ? styles.optionRowDisabled : ""}`}
              >
                <Checkbox checked={checked} disabled={disabled} onChange={() => onToggle(opt.id)} />
                <div className={styles.optionBody}>
                  <span className={styles.optionTitle}>{opt.primary}</span>
                  {opt.secondary ? (
                    <span className={styles.optionSubtle}>{opt.secondary}</span>
                  ) : null}
                </div>
              </label>
            );
          })
        )}
      </div>
    </>
  );
}
