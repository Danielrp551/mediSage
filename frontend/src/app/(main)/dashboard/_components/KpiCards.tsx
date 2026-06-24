"use client";

/**
 * Fila de KPI cards (escalares de `KpiSummary`). Texto puro → pinta primero (contribuye
 * al LCP; no usa `next/dynamic`). Las tasas (fracción 0–1) van en color de marca; los
 * conteos, neutros. `bot_cost_usd` NO va aquí (va en el mini-panel chatbot). La flecha de
 * tendencia vs período anterior es diferible (no MVP).
 */

import {
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  Button,
  Skeleton,
  SkeletonItem,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import type { KpiSummary } from "@/types/dashboards.types";

import { chatbotShare, formatInt, formatPct, formatPctInt } from "./format";

const useStyles = makeStyles({
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: tokens.spacingHorizontalM,
  },
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalL}`,
    backgroundColor: appTokens.contentBg,
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    boxShadow: tokens.shadow2,
  },
  value: {
    fontSize: tokens.fontSizeHero800,
    fontWeight: tokens.fontWeightSemibold,
    lineHeight: tokens.lineHeightHero800,
    color: appTokens.chromeText,
    fontVariantNumeric: "tabular-nums",
    letterSpacing: "-0.02em",
  },
  valueBrand: { color: tokens.colorBrandForeground1 },
  label: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  },
  dim: { opacity: 0.55, transition: "opacity 150ms ease" },
});

interface KpiDef {
  key: string;
  label: string;
  value: (s: KpiSummary) => string;
  brand?: boolean;
}

const KPIS: KpiDef[] = [
  {
    key: "conversion",
    label: "Tasa de conversión",
    value: (s) => formatPct(s.conversion_rate),
    brand: true,
  },
  { key: "leads", label: "Leads", value: (s) => formatInt(s.total_leads) },
  { key: "appointments", label: "Citas", value: (s) => formatInt(s.total_appointments) },
  { key: "confirmed", label: "Confirmadas", value: (s) => formatInt(s.total_confirmed) },
  { key: "customers", label: "Clientes", value: (s) => formatInt(s.total_customers) },
  { key: "bot", label: "Aporte bot", value: (s) => formatPctInt(chatbotShare(s)), brand: true },
];

interface Props {
  summary: KpiSummary | undefined;
  isLoading: boolean;
  isRefetching: boolean;
  isError: boolean;
  onRetry: () => void;
}

export function KpiCards({ summary, isLoading, isRefetching, isError, onRetry }: Props) {
  const styles = useStyles();

  if (isError) {
    return (
      <MessageBar intent="error">
        <MessageBarBody>No se pudieron cargar los indicadores.</MessageBarBody>
        <MessageBarActions
          containerAction={
            <Button appearance="transparent" size="small" onClick={onRetry}>
              Reintentar
            </Button>
          }
        />
      </MessageBar>
    );
  }

  if (isLoading || !summary) {
    return (
      <div className={styles.grid}>
        {KPIS.map((k) => (
          <div key={k.key} className={styles.card}>
            <Skeleton>
              <SkeletonItem style={{ height: 36, width: "70%" }} />
            </Skeleton>
            <span className={styles.label}>{k.label}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={mergeClasses(styles.grid, isRefetching && styles.dim)}>
      {KPIS.map((k) => (
        <div key={k.key} className={styles.card}>
          <span className={mergeClasses(styles.value, k.brand && styles.valueBrand)}>
            {k.value(summary)}
          </span>
          <span className={styles.label}>{k.label}</span>
        </div>
      ))}
    </div>
  );
}
