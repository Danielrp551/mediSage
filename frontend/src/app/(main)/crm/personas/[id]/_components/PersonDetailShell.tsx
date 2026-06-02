"use client";

import {
  Avatar,
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
import type { PersonDetail } from "@/types/crm.types";

import { ActivityTimeline } from "./ActivityTimeline";
import { CustomerTab } from "./CustomerTab";
import { IdentifiersTab } from "./IdentifiersTab";
import { LeadTab } from "./LeadTab";
import { PersonAuditTab } from "./PersonAuditTab";
import { PersonSummaryTab } from "./PersonSummaryTab";
import { StatusBadge } from "./StatusBadge";

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
  advisorBadge: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
});

type TabId = "summary" | "identifiers" | "lead" | "customer" | "activity" | "audit";
const TAB_ORDER: TabId[] = ["summary", "identifiers", "lead", "customer", "activity", "audit"];

interface Props {
  person: PersonDetail;
  initialTab: TabId;
}

export function PersonDetailShell({ person, initialTab }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();

  // Actividad sólo se renderiza con LEAD_ACTIVITIES_READ (ui.md). Resumen /
  // Identificadores / Lead / Cliente / Auditoría se ven con PERSONS_READ (que el
  // RSC ya garantizó). F3 funcionaliza Lead (estado + transición + history) y
  // Actividad (feed read-only); F4 funcionaliza Cliente (estado + transición +
  // history; la promoción nace desde el tab Lead).
  const canReadActivity = hasPermission("LEAD_ACTIVITIES_READ");

  const [tabParam, setTabParam] = useQueryState("tab", { defaultValue: initialTab });

  const allowed: Record<TabId, boolean> = {
    summary: true,
    identifiers: true,
    lead: true,
    customer: true,
    activity: canReadActivity,
    audit: true,
  };
  const tab: TabId = TAB_ORDER.includes(tabParam as TabId) ? (tabParam as TabId) : "summary";
  const activeTab: TabId = allowed[tab] ? tab : "summary";

  // PersonDetail no trae `primary_identifier` denormalizado (eso es de PersonItem);
  // lo derivamos de los identifiers embebidos (el principal preferido, o el
  // primero) para el subtítulo del header.
  const primaryIdentifier =
    person.identifiers.find((i) => i.is_primary) ?? person.identifiers[0] ?? null;

  const subtitleParts = [
    primaryIdentifier?.identifier ?? null,
    person.document_number
      ? `${person.document_type ? `${person.document_type} ` : ""}${person.document_number}`
      : null,
    person.address,
  ].filter(Boolean);

  return (
    <div className={styles.root}>
      <div className={styles.backRow}>
        <Link href="/crm/personas" className={styles.backLink}>
          <ArrowLeftRegular />
          Volver a contactos
        </Link>
      </div>

      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{person.full_name}</h1>
          {/* F3/F4: lead_status/customer_status/assigned_advisor ya se pueblan. Los
              badges de estado usan StatusBadge (contraste por luminancia sobre el
              color del catálogo); el de cliente llega con F4. */}
          {person.lead_status ? <StatusBadge status={person.lead_status} /> : null}
          {person.customer_status ? <StatusBadge status={person.customer_status} /> : null}
          {person.assigned_advisor ? (
            <span className={styles.advisorBadge}>
              <Avatar size={20} name={person.assigned_advisor.full_name} color="colorful" />
              {person.assigned_advisor.full_name}
            </span>
          ) : null}
          <Badge appearance="filled" color={person.active ? "success" : "informative"}>
            {person.active ? "Activo" : "Inactivo"}
          </Badge>
        </div>
        {subtitleParts.length > 0 ? (
          <p className={styles.subtitle}>{subtitleParts.join(" · ")}</p>
        ) : null}
      </header>

      <TabList
        selectedValue={activeTab}
        onTabSelect={(_e: SelectTabEvent, d: SelectTabData) => void setTabParam(d.value as TabId)}
      >
        <Tab value="summary">Resumen</Tab>
        <Tab value="identifiers">Identificadores</Tab>
        <Tab value="lead">Lead</Tab>
        <Tab value="customer">Cliente</Tab>
        {canReadActivity ? <Tab value="activity">Actividad</Tab> : null}
        <Tab value="audit">Auditoría</Tab>
      </TabList>

      {activeTab === "summary" ? (
        <PersonSummaryTab person={person} />
      ) : activeTab === "identifiers" ? (
        <IdentifiersTab personId={person.id} canWrite={hasPermission("PERSONS_UPDATE")} />
      ) : activeTab === "lead" ? (
        <LeadTab
          personId={person.id}
          canWrite={hasPermission("LEAD_ACTIVITIES_WRITE")}
          canReadHistory={hasPermission("LEAD_STATUS_HISTORY_READ")}
        />
      ) : activeTab === "customer" ? (
        <CustomerTab
          personId={person.id}
          canWrite={hasPermission("LEAD_ACTIVITIES_WRITE")}
          canReadHistory={hasPermission("LEAD_STATUS_HISTORY_READ")}
        />
      ) : activeTab === "activity" ? (
        <ActivityTimeline personId={person.id} canWrite={hasPermission("LEAD_ACTIVITIES_WRITE")} />
      ) : (
        <PersonAuditTab person={person} />
      )}
    </div>
  );
}
