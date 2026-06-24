"use client";

/**
 * Embudo de conversión bespoke (precedente "bespoke dentro de Fluent" = `CalendarGrid`).
 * Barras horizontales decrecientes (ancho ∝ conteo, relativo a la etapa de mayor volumen)
 * con el conteo + la tasa etapa-a-etapa (`rate_from_prev`) a la derecha. Es DIVS + tokens
 * Fluent → renderiza inmediato con el prefetch del RSC (sin el bundle de charts), lo que
 * ayuda al LCP del widget protagonista (HU26).
 *
 * Colores: el embudo NO mapea 1:1 a un estado de catálogo → usa una rampa del azul de marca
 * (Bold blue), NO `stage.color`. (El donut y la línea SÍ usan los colores del catálogo.)
 */

import { Tooltip, makeStyles, tokens } from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import type { FunnelSummary } from "@/types/dashboards.types";

import { formatInt, formatPctUncapped } from "./format";

// Rampa de 6 tonos del azul de marca (#0F6CBD = brandPalette.primary, idx 3). Claro arriba
// (mayor volumen) → oscuro abajo (a medida que el embudo se angosta). Tokens de data-viz
// derivados de la marca; no es un hex "fuera del design system".
const FUNNEL_RAMP = ["#5AA0DE", "#3D8AD2", "#2275C4", "#0F6CBD", "#115EA3", "#0E4775"];

const MIN_BAR_PCT = 6; // ancho mínimo para que una etapa con conteo chico siga siendo visible

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  row: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalM },
  label: {
    width: "168px",
    flexShrink: 0,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  track: { flex: 1, minWidth: 0 },
  bar: {
    height: "28px",
    borderRadius: tokens.borderRadiusMedium,
    minWidth: "8px",
    transition: "width 320ms cubic-bezier(0.23, 1, 0.32, 1)",
  },
  values: {
    width: "104px",
    flexShrink: 0,
    display: "flex",
    alignItems: "baseline",
    justifyContent: "flex-end",
    gap: tokens.spacingHorizontalXS,
  },
  count: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    fontVariantNumeric: "tabular-nums",
  },
  rate: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    fontVariantNumeric: "tabular-nums",
    minWidth: "34px",
    textAlign: "right",
  },
});

export function ConversionFunnel({ data }: { data: FunnelSummary }) {
  const styles = useStyles();
  const base = Math.max(...data.stages.map((s) => s.count), 1);

  return (
    <div className={styles.root}>
      {data.stages.map((stage, i) => {
        const pct = Math.max(MIN_BAR_PCT, (stage.count / base) * 100);
        const color = FUNNEL_RAMP[Math.min(i, FUNNEL_RAMP.length - 1)];
        const rateText =
          stage.rate_from_prev != null ? formatPctUncapped(stage.rate_from_prev) : "";
        const tip =
          stage.rate_from_prev != null
            ? `${stage.label}: ${formatInt(stage.count)} (${rateText} vs etapa previa)`
            : `${stage.label}: ${formatInt(stage.count)}`;
        return (
          <div key={stage.key} className={styles.row}>
            <span className={styles.label} title={stage.label}>
              {stage.label}
            </span>
            <div className={styles.track}>
              <Tooltip content={tip} relationship="label" withArrow>
                <div
                  className={styles.bar}
                  style={{ width: `${pct}%`, backgroundColor: color }}
                  role="img"
                  aria-label={tip}
                />
              </Tooltip>
            </div>
            <span className={styles.values}>
              <span className={styles.count}>{formatInt(stage.count)}</span>
              <span className={styles.rate}>{rateText}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
