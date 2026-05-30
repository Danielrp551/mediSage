"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import { CalendarLtrRegular } from "@fluentui/react-icons";

import { appTokens } from "@/lib/theme/brand";
import type { BranchOption } from "@/types/clinic.types";

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalXXXL,
    border: `1px dashed ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    color: appTokens.chromeTextMuted,
    textAlign: "center",
  },
  icon: { fontSize: "40px", color: appTokens.chromeTextMuted, opacity: 0.7 },
  title: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  message: { fontSize: tokens.fontSizeBase300, maxWidth: "360px" },
});

interface Props {
  doctorId: string;
  doctorBranches: BranchOption[];
  canWrite: boolean;
}

// PLACEHOLDER — la grilla semanal de disponibilidad llega en F2. Este tab solo
// muestra un estado vacío "próximamente"; no hace data fetching. Las props se
// declaran tal cual las consumirá F2 (doctorId / doctorBranches / canWrite).
export function DoctorAvailabilityTab(_props: Props) {
  const styles = useStyles();
  return (
    <div className={styles.card}>
      <CalendarLtrRegular className={styles.icon} />
      <div className={styles.title}>Disponibilidad — próximamente</div>
      <div className={styles.message}>
        La grilla semanal de disponibilidad estará disponible en una próxima entrega.
      </div>
    </div>
  );
}
