"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import { CalendarRegular } from "@fluentui/react-icons";

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

// Phase 4 replaces this placeholder with the closures CRUD (cierres / aperturas).
export function OfficeClosuresTab() {
  const styles = useStyles();
  return (
    <div className={styles.placeholder}>
      <CalendarRegular className={styles.icon} />
      <span className={styles.title}>Excepciones</span>
      <span>La gestión de excepciones estará disponible próximamente.</span>
    </div>
  );
}
