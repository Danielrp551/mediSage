"use client";

import {
  Badge,
  Tab,
  TabList,
  makeStyles,
  tokens,
  type SelectTabData,
  type SelectTabEvent,
} from "@fluentui/react-components";
import { ArrowLeftRegular } from "@fluentui/react-icons";
import Link from "next/link";
import { useQueryState } from "nuqs";

import { usePermissions } from "@/hooks/usePermissions";
import { appTokens } from "@/lib/theme/brand";
import type { VerticalOption } from "@/types/catalog.types";
import type { OfficeDetail } from "@/types/clinic.types";

import { OfficeAuditTab } from "./OfficeAuditTab";
import { OfficeClosuresTab } from "./OfficeClosuresTab";
import { OfficeDetailsTab } from "./OfficeDetailsTab";
import { OfficeHoursTab } from "./OfficeHoursTab";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  backRow: { display: "flex" },
  backLink: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    color: appTokens.chromeTextMuted,
    textDecoration: "none",
    fontSize: tokens.fontSizeBase300,
    "&:hover": { color: appTokens.chromeText },
  },
  header: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  titleRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalM },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: 0, fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
});

type TabId = "details" | "hours" | "closures" | "audit";

interface Props {
  office: OfficeDetail;
  verticals: VerticalOption[];
  initialTab: TabId;
}

export function OfficeDetailShell({ office, verticals, initialTab }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();

  const canReadHours = hasPermission("OFFICE_HOURS_READ");
  const canReadClosures = hasPermission("OFFICE_CLOSURES_READ");

  const [tabParam, setTabParam] = useQueryState("tab", { defaultValue: initialTab });

  // Resolve the active tab, falling back to "details" if the URL points at a
  // tab the user can't read (or an unknown value).
  const allowed: Record<TabId, boolean> = {
    details: true,
    hours: canReadHours,
    closures: canReadClosures,
    audit: true,
  };
  const tab: TabId = (["details", "hours", "closures", "audit"] as TabId[]).includes(
    tabParam as TabId,
  )
    ? (tabParam as TabId)
    : "details";
  const activeTab: TabId = allowed[tab] ? tab : "details";

  const subtitleParts = [
    `Sede ${office.branch.name}`,
    office.code,
    office.floor ? `Piso ${office.floor}` : null,
  ].filter(Boolean);

  return (
    <div className={styles.root}>
      <div className={styles.backRow}>
        <Link href="/clinic/offices" className={styles.backLink}>
          <ArrowLeftRegular />
          Volver a consultorios
        </Link>
      </div>

      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{office.name}</h1>
          <Badge appearance="filled" color={office.active ? "success" : "informative"}>
            {office.active ? "Activo" : "Deshabilitado"}
          </Badge>
        </div>
        <p className={styles.subtitle}>{subtitleParts.join(" · ")}</p>
      </header>

      <TabList
        selectedValue={activeTab}
        onTabSelect={(_e: SelectTabEvent, d: SelectTabData) => void setTabParam(d.value as TabId)}
      >
        <Tab value="details">Detalles</Tab>
        {canReadHours ? <Tab value="hours">Horarios</Tab> : null}
        {canReadClosures ? <Tab value="closures">Excepciones</Tab> : null}
        <Tab value="audit">Auditoría</Tab>
      </TabList>

      {activeTab === "details" ? (
        <OfficeDetailsTab office={office} verticals={verticals} />
      ) : activeTab === "hours" ? (
        <OfficeHoursTab officeId={office.id} branchTimezone={office.branch.timezone} />
      ) : activeTab === "closures" ? (
        <OfficeClosuresTab officeId={office.id} branchTimezone={office.branch.timezone} />
      ) : (
        <OfficeAuditTab office={office} />
      )}
    </div>
  );
}
