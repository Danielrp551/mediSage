"use client";

import { Badge, Divider, makeStyles, tokens } from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { OfficeDetail } from "@/types/clinic.types";

const useStyles = makeStyles({
  panel: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    maxWidth: "720px",
  },
  audit: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    fontSize: tokens.fontSizeBase200,
  },
  auditLabel: { color: appTokens.chromeTextMuted, fontSize: tokens.fontSizeBase200 },
  auditValue: { color: appTokens.chromeText, fontWeight: tokens.fontWeightMedium },
});

interface Props {
  office: OfficeDetail;
}

export function OfficeAuditTab({ office }: Props) {
  const styles = useStyles();
  return (
    <div className={styles.panel}>
      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Estado</div>
          <div className={styles.auditValue}>
            <Badge appearance="filled" color={office.active ? "success" : "informative"}>
              {office.active ? "Activo" : "Deshabilitado"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID del consultorio</div>
          <div className={styles.auditValue}>
            <code>{office.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creado el</div>
          <div className={styles.auditValue}>{formatDate(office.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creado por</div>
          <div className={styles.auditValue}>{office.created_by_user?.full_name ?? "—"}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado el</div>
          <div className={styles.auditValue}>{formatDate(office.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado por</div>
          <div className={styles.auditValue}>{office.updated_by_user?.full_name ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}
