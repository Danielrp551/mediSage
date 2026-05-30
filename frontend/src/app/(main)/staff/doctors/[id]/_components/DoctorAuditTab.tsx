"use client";

import { Badge, Divider, makeStyles, tokens } from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { DoctorDetail } from "@/types/staff.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "640px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    fontSize: tokens.fontSizeBase200,
  },
  label: { color: appTokens.chromeTextMuted, fontSize: tokens.fontSizeBase200 },
  value: { color: appTokens.chromeText, fontWeight: tokens.fontWeightMedium },
  cell: { display: "flex", flexDirection: "column", gap: "2px" },
});

export function DoctorAuditTab({ doctor }: { doctor: DoctorDetail }) {
  const styles = useStyles();
  return (
    <div className={styles.root}>
      <div className={styles.grid}>
        <div className={styles.cell}>
          <span className={styles.label}>Estado</span>
          <span className={styles.value}>
            <Badge appearance="filled" color={doctor.active ? "success" : "informative"}>
              {doctor.active ? "Activo" : "Inactivo"}
            </Badge>
          </span>
        </div>
        <div className={styles.cell}>
          <span className={styles.label}>ID del doctor</span>
          <span className={styles.value}>
            <code>{doctor.id}</code>
          </span>
        </div>
        <div className={styles.cell}>
          <span className={styles.label}>Usuario (1:1)</span>
          <span className={styles.value}>
            <code>{doctor.user_id}</code>
          </span>
        </div>
      </div>

      <Divider />

      <div className={styles.grid}>
        <div className={styles.cell}>
          <span className={styles.label}>Creado el</span>
          <span className={styles.value}>{formatDate(doctor.created_on)}</span>
        </div>
        <div className={styles.cell}>
          <span className={styles.label}>Creado por</span>
          <span className={styles.value}>{doctor.created_by_user?.full_name ?? "—"}</span>
        </div>
        <div className={styles.cell}>
          <span className={styles.label}>Actualizado el</span>
          <span className={styles.value}>{formatDate(doctor.updated_on)}</span>
        </div>
        <div className={styles.cell}>
          <span className={styles.label}>Actualizado por</span>
          <span className={styles.value}>{doctor.updated_by_user?.full_name ?? "—"}</span>
        </div>
      </div>
    </div>
  );
}
