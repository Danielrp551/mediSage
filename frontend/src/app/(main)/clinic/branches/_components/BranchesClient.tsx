"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  DeleteRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { deleteBranch, listBranches } from "@/actions/branch.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { BranchItem } from "@/types/clinic.types";

import { BranchDrawer } from "./BranchDrawer";

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
});

interface Props {
  initialData: ApiPaginated<BranchItem>;
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; branchId: string | null } | null;

export function BranchesClient({ initialData }: Props) {
  const styles = useStyles();
  const table = useTableQuery<BranchItem>({
    queryKey: "clinic:branches",
    fetcher: listBranches,
    defaultSort: { field: "name", order: "asc" },
    searchFields: ["code", "name", "city"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<BranchItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<BranchItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (b) => setDrawer({ mode: "view", branchId: b.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["BRANCHES_UPDATE"],
        onSelect: (b) => setDrawer({ mode: "edit", branchId: b.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["BRANCHES_DELETE"],
        danger: true,
        onSelect: (b) => {
          setDeleteError(null);
          setDeleteTarget(b);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteBranch(deleteTarget.id);
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
        <h1 className={styles.title}>Sedes</h1>
        <p className={styles.subtitle}>Gestiona las sedes físicas de la clínica.</p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por código, nombre o ciudad…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["BRANCHES_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", branchId: null })}
          >
            Nueva sede
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<BranchItem>
        items={data.data.items}
        getRowKey={(b) => b.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay sedes"
        emptyMessage="Crea la primera sede para empezar a configurar la clínica."
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
            onRender: (b) => <RowActions item={b} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Código",
            fieldName: "code",
            isSortable: true,
            truncate: true,
            minWidth: 180,
          },
          {
            key: "name",
            name: "Nombre",
            fieldName: "name",
            isSortable: true,
            truncate: true,
            minWidth: 220,
          },
          {
            key: "city",
            name: "Ciudad",
            fieldName: "city",
            isSortable: true,
            truncate: true,
            minWidth: 140,
          },
          {
            key: "offices_count",
            name: "Consultorios",
            fieldName: "offices_count",
            numeric: true,
            minWidth: 120,
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (b) => (
              <Badge appearance="filled" color={b.active ? "success" : "informative"}>
                {b.active ? "Activa" : "Deshabilitada"}
              </Badge>
            ),
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 180,
            onRender: (b) => formatDate(b.updated_on),
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
        <BranchDrawer
          mode={drawer.mode}
          branchId={drawer.branchId}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar sede?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar la sede "${deleteTarget.name}"? Esta acción se puede revertir recreándola.`
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
