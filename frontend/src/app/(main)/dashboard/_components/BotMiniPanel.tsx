"use client";

/**
 * Mini-panel del chatbot — resalta el aporte del bot (eje de la tesis). Cifras de `KpiSummary`:
 * conversaciones del bot, turnos, costo estimado (`bot_cost_usd` es STRING → se formatea, no se
 * opera crudo) y % de citas que vienen del bot. El "nº de mensajes" NO se muestra (los mensajes
 * viven en Firestore, ADR-011 → no agregables en SQL; los proxies son conversaciones + turnos).
 * Comparte la query de `summary` con las KPI cards (su estado loading/error es el mismo).
 */

import { Skeleton, SkeletonItem, makeStyles, tokens } from "@fluentui/react-components";
import { BotRegular } from "@fluentui/react-icons";

import { appTokens } from "@/lib/theme/brand";
import type { KpiSummary } from "@/types/dashboards.types";

import { chatbotShare, formatInt, formatPctInt, formatUsd } from "./format";

const useStyles = makeStyles({
  surface: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalL,
    backgroundColor: appTokens.contentBg,
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    boxShadow: tokens.shadow2,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  headerIcon: { color: tokens.colorBrandForeground1, fontSize: "20px", display: "inline-flex" },
  body: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXXL,
    flexWrap: "wrap",
  },
  stat: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  statValue: {
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    fontVariantNumeric: "tabular-nums",
    lineHeight: tokens.lineHeightHero700,
  },
  statLabel: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  },
  share: {
    marginLeft: "auto",
    display: "flex",
    alignItems: "baseline",
    gap: tokens.spacingHorizontalXS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase300,
  },
  shareValue: {
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorBrandForeground1,
    fontVariantNumeric: "tabular-nums",
  },
  note: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
});

interface Props {
  summary: KpiSummary | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function BotMiniPanel({ summary, isLoading, isError }: Props) {
  const styles = useStyles();

  return (
    <section className={styles.surface}>
      <div className={styles.header}>
        <span className={styles.headerIcon}>
          <BotRegular />
        </span>
        Atención del bot
      </div>

      {isError ? (
        <span className={styles.note}>Información del bot no disponible por ahora.</span>
      ) : isLoading || !summary ? (
        <Skeleton>
          <SkeletonItem style={{ height: 44, width: "60%" }} />
        </Skeleton>
      ) : (
        <>
          <div className={styles.body}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{formatInt(summary.conversations_bot)}</span>
              <span className={styles.statLabel}>Conversaciones</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{formatInt(summary.bot_turns)}</span>
              <span className={styles.statLabel}>Turnos</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{formatUsd(summary.bot_cost_usd)}</span>
              <span className={styles.statLabel}>Costo estimado</span>
            </div>
            <div className={styles.share}>
              <span className={styles.shareValue}>{formatPctInt(chatbotShare(summary))}</span>
              <span>de las citas vienen del bot</span>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
