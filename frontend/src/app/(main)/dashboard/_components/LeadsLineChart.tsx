"use client";

/**
 * Evolución de leads (línea bespoke en SVG). Una serie por estado de lead (color del catálogo
 * `lead_status.color`, ADR-008; fallback a tokens). SSR-safe y sin dependencia de charts: el
 * `<svg viewBox>` con `preserveAspectRatio="none"` escala al ancho del contenedor y los trazos
 * usan `vector-effect: non-scaling-stroke` para no distorsionarse; los rótulos de ejes son HTML
 * (nítidos). El eje X son fechas-puro del rollup formateadas SIN `Date` (determinista, sin TZ).
 */

import { makeStyles, tokens } from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import type { TimeSeries } from "@/types/dashboards.types";

import { formatDayMonth, formatInt } from "./format";

const FALLBACK_COLORS = [
  tokens.colorBrandForeground1,
  tokens.colorPaletteGreenForeground1,
  tokens.colorPaletteMarigoldForeground1,
  tokens.colorPalettePurpleForeground2,
  tokens.colorPaletteBerryForeground1,
  tokens.colorPaletteTealForeground2,
];

const PLOT_HEIGHT = 220;

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  legend: {
    display: "flex",
    flexWrap: "wrap",
    gap: tokens.spacingHorizontalL,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeText,
  },
  legendItem: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalXS },
  legendSwatch: { width: "16px", height: "3px", borderRadius: "2px", flexShrink: 0 },
  plot: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gridTemplateRows: "auto auto",
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalXXS,
  },
  yAxis: {
    gridColumn: 1,
    gridRow: 1,
    height: `${PLOT_HEIGHT}px`,
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    alignItems: "flex-end",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    fontVariantNumeric: "tabular-nums",
  },
  svg: { gridColumn: 2, gridRow: 1, width: "100%", height: `${PLOT_HEIGHT}px`, display: "block" },
  xAxis: {
    gridColumn: 2,
    gridRow: 2,
    display: "flex",
    justifyContent: "space-between",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
});

export function LeadsLineChart({ data }: { data: TimeSeries | undefined }) {
  const styles = useStyles();
  if (!data || data.points.length === 0) return null;

  const points = [...data.points].sort((a, b) => a.date.localeCompare(b.date));
  const n = points.length;
  const colorOf = (i: number, color: string | null) =>
    color ?? FALLBACK_COLORS[i % FALLBACK_COLORS.length];

  const maxY = Math.max(1, ...points.flatMap((p) => data.series.map((s) => p.values[s.key] ?? 0)));
  const xAt = (i: number) => (n === 1 ? 50 : (i / (n - 1)) * 100);
  const yAt = (v: number) => 100 - (v / maxY) * 100;

  const xLabels =
    n === 1
      ? [formatDayMonth(points[0]!.date)]
      : n === 2
        ? [formatDayMonth(points[0]!.date), formatDayMonth(points[n - 1]!.date)]
        : [
            formatDayMonth(points[0]!.date),
            formatDayMonth(points[Math.floor((n - 1) / 2)]!.date),
            formatDayMonth(points[n - 1]!.date),
          ];

  return (
    <div className={styles.root}>
      <div className={styles.legend}>
        {data.series.map((s, i) => (
          <span key={s.key} className={styles.legendItem}>
            <span
              className={styles.legendSwatch}
              style={{ backgroundColor: colorOf(i, s.color) }}
              aria-hidden
            />
            {s.label}
          </span>
        ))}
      </div>

      <div className={styles.plot}>
        <div className={styles.yAxis}>
          <span>{formatInt(maxY)}</span>
          <span>{formatInt(Math.round(maxY / 2))}</span>
          <span>0</span>
        </div>

        <svg
          className={styles.svg}
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          role="img"
          aria-label="Evolución de leads por día"
        >
          {[0, 50, 100].map((y) => (
            <line
              key={y}
              x1={0}
              y1={y}
              x2={100}
              y2={y}
              style={{ stroke: tokens.colorNeutralStroke2 }}
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {data.series.map((s, i) => {
            const d = points
              .map((p, idx) => `${idx === 0 ? "M" : "L"} ${xAt(idx)} ${yAt(p.values[s.key] ?? 0)}`)
              .join(" ");
            return (
              <path
                key={s.key}
                d={d}
                fill="none"
                style={{ stroke: colorOf(i, s.color) }}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              >
                <title>{s.label}</title>
              </path>
            );
          })}
        </svg>

        <div className={styles.xAxis}>
          {xLabels.map((label, i) => (
            <span key={`${label}-${i}`}>{label}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
