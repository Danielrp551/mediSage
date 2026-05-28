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

import { deleteVertical, listVerticals } from "@/actions/vertical.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { VerticalItem } from "@/types/catalog.types";
import { VerticalDrawer } from "./VerticalDrawer";

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
  subtitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
  },
  toolbar: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  search: { flex: 1, maxWidth: "360px" },
  colorCell: {
    display: "inline-block",
    width: "14px",
    height: "14px",
    borderRadius: tokens.borderRadiusCircular,
    border: `1px solid ${appTokens.chromeBorder}`,
    verticalAlign: "middle",
  },
  colorEmpty: {
    border: `1px dashed ${appTokens.chromeBorder}`,
    background: "transparent",
  },
});

interface Props {
  initialData: ApiPaginated<VerticalItem>;
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; verticalId: string | null } | null;

export function VerticalsClient({ initialData }: Props) {
  const styles = useStyles();
  const table = useTableQuery<VerticalItem>({
    queryKey: "catalog:verticals",
    fetcher: listVerticals,
    defaultSort: { field: "display_order", order: "asc" },
    searchFields: ["code", "name"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<VerticalItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<VerticalItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (v) => setDrawer({ mode: "view", verticalId: v.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["VERTICALS_UPDATE"],
        onSelect: (v) => setDrawer({ mode: "edit", verticalId: v.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["VERTICALS_DELETE"],
        danger: true,
        onSelect: (v) => {
          setDeleteError(null);
          setDeleteTarget(v);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteVertical(deleteTarget.id);
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
        <h1 className={styles.title}>Verticales</h1>
        <p className={styles.subtitle}>
          Gestiona las áreas comerciales principales de la clínica.
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
        <PermissionGuard anyOf={["VERTICALS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", verticalId: null })}
          >
            Nueva vertical
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<VerticalItem>
        items={data.data.items}
        getRowKey={(v) => v.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay verticales"
        emptyMessage="Crea la primera para empezar a construir el catálogo."
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
            onRender: (v) => <RowActions item={v} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Código",
            fieldName: "code",
            isSortable: true,
            truncate: true,
            minWidth: 200,
          },
          {
            key: "name",
            name: "Nombre",
            fieldName: "name",
            isSortable: true,
            truncate: true,
            minWidth: 240,
          },
          {
            key: "color",
            name: "Color",
            align: "center",
            minWidth: 80,
            onRender: (v) => (
              <span
                className={`${styles.colorCell} ${v.color ? "" : styles.colorEmpty}`}
                style={v.color ? { background: v.color } : undefined}
                aria-label={v.color ?? "sin color"}
              />
            ),
          },
          {
            key: "services_count",
            name: "Servicios",
            fieldName: "services_count",
            numeric: true,
            minWidth: 100,
          },
          {
            key: "products_count",
            name: "Productos",
            fieldName: "products_count",
            numeric: true,
            minWidth: 100,
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (v) => (
              <Badge appearance="filled" color={v.active ? "success" : "informative"}>
                {v.active ? "Activa" : "Deshabilitada"}
              </Badge>
            ),
          },
          {
            key: "display_order",
            name: "Orden",
            fieldName: "display_order",
            numeric: true,
            isSortable: true,
            minWidth: 90,
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 180,
            onRender: (v) => formatDate(v.updated_on),
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
        <VerticalDrawer
          mode={drawer.mode}
          verticalId={drawer.verticalId}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar vertical?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar la vertical "${deleteTarget.name}"? Los servicios y productos asociados se conservan. Podrás recrearla más adelante.`
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
