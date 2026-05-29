"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import { ClockRegular } from "@fluentui/react-icons";

import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  placeholder: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
  },
  icon: { fontSize: "32px", color: appTokens.chromeTextMuted },
  title: { fontSize: tokens.fontSizeBase400, fontWeight: tokens.fontWeightSemibold },
});

// Phase 3 replaces this placeholder with the weekly pattern editor (bulk PUT).
export function OfficeHoursTab() {
  const styles = useStyles();
  return (
    <div className={styles.placeholder}>
      <ClockRegular className={styles.icon} />
      <span className={styles.title}>Horario semanal</span>
      <span>El editor de horarios estará disponible próximamente.</span>
    </div>
  );
}
