"use client";

/**
 * Distribución de citas (donut bespoke). Anillo con `conic-gradient` + agujero central con el
 * total; leyenda al lado. Es DIVS + tokens Fluent (precedente "bespoke dentro de Fluent" =
 * `CalendarGrid`/`ConversionFunnel`) → SSR-safe, liviano y sin dependencia de charts. Los colores
 * de segmento salen del catálogo `appointment_status.color` (ADR-008); si un estado no trae color,
 * cae a una rampa de tokens de marca/paleta (CSS vars, válidas dentro de `conic-gradient`).
 */

import { makeStyles, tokens } from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import type { DistributionSummary } from "@/types/dashboards.types";

import { formatInt } from "./format";

// Fallback para estados sin color en el catálogo (CSS vars → resuelven dentro del conic-gradient).
const FALLBACK_COLORS = [
  tokens.colorBrandBackground,
  tokens.colorPaletteGreenForeground1,
  tokens.colorPaletteMarigoldForeground1,
  tokens.colorPalettePurpleForeground2,
  tokens.colorPaletteBerryForeground1,
  tokens.colorPaletteTealForeground2,
];

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXXL,
    flexWrap: "wrap",
  },
  donutWrap: { position: "relative", width: "180px", height: "180px", flexShrink: 0 },
  donut: { width: "180px", height: "180px", borderRadius: "50%" },
  hole: {
    position: "absolute",
    top: "30px",
    left: "30px",
    right: "30px",
    bottom: "30px",
    borderRadius: "50%",
    backgroundColor: appTokens.contentBg,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  holeTotal: {
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    fontVariantNumeric: "tabular-nums",
    lineHeight: tokens.lineHeightHero700,
  },
  holeLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  legend: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS, minWidth: 0 },
  legendItem: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
  },
  swatch: { width: "12px", height: "12px", borderRadius: tokens.borderRadiusSmall, flexShrink: 0 },
  legendLabel: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  legendCount: {
    marginLeft: "auto",
    paddingLeft: tokens.spacingHorizontalM,
    fontWeight: tokens.fontWeightSemibold,
    fontVariantNumeric: "tabular-nums",
  },
});

export function AppointmentsDonut({ data }: { data: DistributionSummary | undefined }) {
  const styles = useStyles();
  if (!data || data.total <= 0) return null;

  let acc = 0;
  const stops: string[] = [];
  const colorOf = (index: number, color: string | null) =>
    color ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length];

  data.buckets.forEach((b, i) => {
    if (b.count <= 0) return;
    const start = (acc / data.total) * 360;
    acc += b.count;
    const end = (acc / data.total) * 360;
    stops.push(`${colorOf(i, b.color)} ${start}deg ${end}deg`);
  });
  const gradient = `conic-gradient(${stops.join(", ")})`;

  return (
    <div className={styles.root}>
      <div className={styles.donutWrap}>
        <div
          className={styles.donut}
          style={{ background: gradient }}
          role="img"
          aria-label="Distribución de citas por estado"
        />
        <div className={styles.hole}>
          <span className={styles.holeTotal}>{formatInt(data.total)}</span>
          <span className={styles.holeLabel}>citas</span>
        </div>
      </div>
      <div className={styles.legend}>
        {data.buckets.map((b, i) => (
          <span key={b.code} className={styles.legendItem}>
            <span
              className={styles.swatch}
              style={{ backgroundColor: colorOf(i, b.color) }}
              aria-hidden
            />
            <span className={styles.legendLabel}>{b.label}</span>
            <span className={styles.legendCount}>{formatInt(b.count)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
