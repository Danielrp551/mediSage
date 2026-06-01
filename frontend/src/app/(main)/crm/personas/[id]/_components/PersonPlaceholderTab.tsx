"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import { SparkleRegular } from "@fluentui/react-icons";

import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  panel: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    textAlign: "center",
    minHeight: "240px",
  },
  icon: { fontSize: "36px", color: appTokens.chromeTextMuted, opacity: 0.7 },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  message: {
    margin: 0,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
    maxWidth: "420px",
    lineHeight: 1.5,
  },
});

interface Props {
  title: string;
  message: string;
}

/** Tab vacío para secciones aún no implementadas (Lead/Cliente/Actividad en F1). */
export function PersonPlaceholderTab({ title, message }: Props) {
  const styles = useStyles();
  return (
    <div className={styles.panel}>
      <SparkleRegular className={styles.icon} />
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.message}>{message}</p>
    </div>
  );
}
