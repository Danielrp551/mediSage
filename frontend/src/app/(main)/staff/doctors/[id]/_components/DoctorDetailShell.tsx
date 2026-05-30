"use client";

import { Badge, Button, Tab, TabList, makeStyles, tokens } from "@fluentui/react-components";
import { ArrowLeftRegular } from "@fluentui/react-icons";
import { useRouter } from "next/navigation";
import { useQueryState } from "nuqs";

import { usePermissions } from "@/hooks/usePermissions";
import { appTokens } from "@/lib/theme/brand";
import type { VerticalOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import type { DoctorDetail } from "@/types/staff.types";

import { DoctorAuditTab } from "./DoctorAuditTab";
import { DoctorAvailabilityTab } from "./DoctorAvailabilityTab";
import { DoctorProfileTab } from "./DoctorProfileTab";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  header: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  backRow: { marginBottom: tokens.spacingVerticalXS },
  titleRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: 0, fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
  meta: {
    display: "flex",
    gap: tokens.spacingHorizontalL,
    flexWrap: "wrap",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
});

const ALLOWED_TABS = ["profile", "availability", "audit"] as const;
type DoctorTab = (typeof ALLOWED_TABS)[number];

interface Props {
  doctor: DoctorDetail;
  branches: BranchOption[];
  verticals: VerticalOption[];
  initialTab: DoctorTab;
}

export function DoctorDetailShell({ doctor, branches, verticals, initialTab }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const { hasPermission } = usePermissions();
  const [tab, setTab] = useQueryState("tab");

  const canSeeAvailability = hasPermission("DOCTOR_AVAILABILITY_READ");

  const resolved: DoctorTab = ALLOWED_TABS.includes(tab as DoctorTab)
    ? (tab as DoctorTab)
    : initialTab;
  // Si la URL pide "availability" sin permiso, caer a "profile".
  const activeTab: DoctorTab =
    resolved === "availability" && !canSeeAvailability ? "profile" : resolved;

  const metaParts = [
    doctor.cmp_code ? `CMP ${doctor.cmp_code}` : null,
    `${doctor.branches_count} sedes`,
    `${doctor.verticals_count} verticales`,
    `${doctor.slot_duration_min} min/slot`,
  ].filter(Boolean) as string[];

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div className={styles.backRow}>
          <Button
            appearance="subtle"
            size="small"
            icon={<ArrowLeftRegular />}
            onClick={() => router.push("/staff/doctors")}
          >
            Volver a doctores
          </Button>
        </div>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{doctor.full_name}</h1>
          <Badge appearance="filled" color={doctor.active ? "success" : "informative"}>
            {doctor.active ? "Activo" : "Inactivo"}
          </Badge>
        </div>
        <p className={styles.subtitle}>{doctor.email}</p>
        <div className={styles.meta}>
          {metaParts.map((part) => (
            <span key={part}>{part}</span>
          ))}
        </div>
      </header>

      <TabList selectedValue={activeTab} onTabSelect={(_, d) => void setTab(d.value as string)}>
        <Tab value="profile">Perfil</Tab>
        {canSeeAvailability ? <Tab value="availability">Disponibilidad</Tab> : null}
        <Tab value="audit">Auditoría</Tab>
      </TabList>

      {activeTab === "profile" ? (
        <DoctorProfileTab doctor={doctor} branches={branches} verticals={verticals} />
      ) : activeTab === "availability" ? (
        <DoctorAvailabilityTab
          doctorId={doctor.id}
          doctorBranches={doctor.branches}
          canWrite={hasPermission("DOCTOR_AVAILABILITY_WRITE")}
        />
      ) : (
        <DoctorAuditTab doctor={doctor} />
      )}
    </div>
  );
}
