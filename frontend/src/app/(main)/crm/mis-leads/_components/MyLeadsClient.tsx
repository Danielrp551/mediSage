"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { listMyLeads } from "@/actions/lead-assignment.actions";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatRelative } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { MyLeadItem } from "@/types/crm.types";

import { StatusBadge } from "../../personas/[id]/_components/StatusBadge";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  header: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: 0, fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
  muted: { color: appTokens.chromeTextMuted },
});

interface Props {
  initialData: ApiPaginated<MyLeadItem>;
}

export function MyLeadsClient({ initialData }: Props) {
  const styles = useStyles();
  const router = useRouter();

  // Las fechas relativas usan `new Date()` (ahora) → cliente-only. Hasta montar,
  // se muestra "—" para evitar el mismatch de hidratación (SSR corre en UTC).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // defaultSort `created_on` — coincide con el prefetch del page.tsx (columna
  // real de Person; los campos de MyLeadItem son denormalizados, no sortables).
  const table = useTableQuery<MyLeadItem>({
    queryKey: "crm:my-leads",
    fetcher: listMyLeads,
    defaultPageSize: 10,
    defaultSort: { field: "created_on", order: "desc" },
    initialData,
  });

  const data = table.query.data ?? initialData;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Mis leads</h1>
        <p className={styles.subtitle}>Los contactos que tienes asignados como asesor.</p>
      </header>

      <DataTable<MyLeadItem>
        items={data.data.items}
        getRowKey={(p) => p.person_id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        emptyTitle="No tienes leads asignados"
        emptyMessage="Cuando se te asigne un contacto aparecerá en esta lista."
        onRowClick={(p) => router.push(`/crm/personas/${p.person_id}`)}
        columns={[
          {
            key: "full_name",
            name: "Contacto",
            fieldName: "full_name",
            truncate: true,
            minWidth: 220,
          },
          {
            key: "lead_status",
            name: "Estado lead",
            minWidth: 150,
            onRender: (p) => <StatusBadge status={p.lead_status} fallback="—" />,
          },
          {
            key: "last_activity_at",
            name: "Última actividad",
            minWidth: 150,
            onRender: (p) =>
              mounted && p.last_activity_at ? (
                formatRelative(p.last_activity_at)
              ) : (
                <span className={styles.muted}>—</span>
              ),
          },
          {
            key: "next_follow_up_at",
            name: "Próximo seguimiento",
            minWidth: 170,
            onRender: (p) =>
              mounted && p.next_follow_up_at ? (
                formatRelative(p.next_follow_up_at)
              ) : (
                <span className={styles.muted}>—</span>
              ),
          },
        ]}
        pagination={{
          page: table.page,
          pageSize: table.pageSize,
          total: data.data.total,
          onPageChange: table.setPage,
          onPageSizeChange: table.setPageSize,
        }}
      />
    </div>
  );
}
