"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import { AddRegular, DeleteRegular, EditRegular, SearchRegular } from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { deleteLeadStatus, listLeadStatuses } from "@/actions/lead-status.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { LeadStatusItem } from "@/types/crm.types";

import { LeadStatusDrawer } from "./LeadStatusDrawer";

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
  toolbar: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  search: { flex: 1, maxWidth: "360px" },
  colorCell: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
  },
  swatch: {
    display: "inline-block",
    width: "14px",
    height: "14px",
    borderRadius: tokens.borderRadiusCircular,
    border: `1px solid ${appTokens.chromeBorder}`,
    flexShrink: 0,
  },
  swatchEmpty: {
    border: `1px dashed ${appTokens.chromeBorder}`,
    background: "transparent",
  },
  hexText: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  flags: { display: "inline-flex", gap: tokens.spacingHorizontalXS, flexWrap: "wrap" },
  mono: { fontFamily: tokens.fontFamilyMonospace },
  muted: { color: appTokens.chromeTextMuted },
});

interface Props {
  initialData: ApiPaginated<LeadStatusItem>;
}

type DrawerState = { mode: "create" | "edit"; status: LeadStatusItem | null } | null;

export function LeadStatusesClient({ initialData }: Props) {
  const styles = useStyles();
  const table = useTableQuery<LeadStatusItem>({
    queryKey: "crm:lead-statuses",
    fetcher: listLeadStatuses,
    // Catálogo chico: una sola página. defaultPageSize debe coincidir con el
    // prefetch (limit:50) para que isDefaultQuery sea true y no haya desync del
    // footer ni flash al primer refetch.
    defaultPageSize: 50,
    // display_order es columna real de ALLOWED_FIELDS → coincide con el prefetch.
    defaultSort: { field: "display_order", order: "asc" },
    searchFields: ["code", "name"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<LeadStatusItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<LeadStatusItem>[]>(
    () => [
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["LEAD_STATUSES_WRITE"],
        onSelect: (s) => setDrawer({ mode: "edit", status: s }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["LEAD_STATUSES_WRITE"],
        danger: true,
        onSelect: (s) => {
          setDeleteError(null);
          setDeleteTarget(s);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteLeadStatus(deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  };

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Estados de lead</h1>
        <p className={styles.subtitle}>
          Configura los estados por los que pasa un lead y sus transiciones.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por código o nombre…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["LEAD_STATUSES_WRITE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", status: null })}
          >
            Nuevo estado
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<LeadStatusItem>
        items={data.data.items}
        getRowKey={(s) => s.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay estados de lead"
        emptyMessage="Crea el primero (marca uno como inicial)."
        sortField={table.sortField}
        sortOrder={table.sortOrder}
        onSort={(field, descending) => table.setSort(field, descending ? "desc" : "asc")}
        columns={[
          {
            key: "actions",
            name: "",
            align: "center",
            minWidth: 48,
            maxWidth: 56,
            onRender: (s) => <RowActions item={s} actions={rowActions} />,
          },
          {
            key: "display_order",
            name: "Orden",
            fieldName: "display_order",
            numeric: true,
            isSortable: true,
            minWidth: 80,
          },
          {
            key: "code",
            name: "Código",
            fieldName: "code",
            isSortable: true,
            truncate: true,
            minWidth: 160,
            onRender: (s) => <span className={styles.mono}>{s.code}</span>,
          },
          {
            key: "name",
            name: "Nombre",
            fieldName: "name",
            isSortable: true,
            truncate: true,
            minWidth: 200,
          },
          {
            key: "color",
            name: "Color",
            minWidth: 130,
            onRender: (s) => (
              <span className={styles.colorCell}>
                <span
                  className={`${styles.swatch} ${s.color ? "" : styles.swatchEmpty}`}
                  style={s.color ? { backgroundColor: s.color } : undefined}
                  aria-label={s.color ?? "sin color"}
                />
                <span className={styles.hexText}>{s.color ?? "—"}</span>
              </span>
            ),
          },
          {
            key: "flags",
            name: "Atributos",
            minWidth: 200,
            onRender: (s) => {
              const hasFlag = s.is_initial || s.is_final || s.is_won;
              if (!hasFlag) return <span className={styles.muted}>—</span>;
              return (
                <span className={styles.flags}>
                  {s.is_initial ? <Badge appearance="tint">Inicial</Badge> : null}
                  {s.is_final ? <Badge appearance="tint">Final</Badge> : null}
                  {s.is_won ? <Badge appearance="tint">Ganado</Badge> : null}
                </span>
              );
            },
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (s) => (
              <Badge appearance="filled" color={s.active ? "success" : "informative"}>
                {s.active ? "Activo" : "Inactivo"}
              </Badge>
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

      {drawer ? (
        <LeadStatusDrawer
          mode={drawer.mode}
          status={drawer.status}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar estado de lead?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el estado "${deleteTarget.name}"? Esta acción no se puede deshacer.`
              : ""
        }
        confirmText={deletePending ? "Eliminando…" : "Eliminar"}
        cancelText="Cancelar"
        destructive
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => {
          if (!deletePending) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
      />
    </div>
  );
}
