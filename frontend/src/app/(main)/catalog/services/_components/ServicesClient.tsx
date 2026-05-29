"use client";

import {
  Badge,
  Button,
  Dropdown,
  Input,
  Option,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  AddRegular,
  DismissRegular,
  DeleteRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { deleteService, listServices } from "@/actions/service.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { ServiceItem, VerticalOption } from "@/types/catalog.types";
import type { FilterCondition } from "@/types/query.types";

import { ServiceDrawer } from "./ServiceDrawer";

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
  verticalFilter: { minWidth: "220px" },
  search: { flex: 1, maxWidth: "360px" },
  chipRow: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    alignItems: "center",
    flexWrap: "wrap",
  },
  chip: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXXS,
    paddingLeft: tokens.spacingHorizontalS,
    backgroundColor: appTokens.chromeBgHover,
    borderRadius: tokens.borderRadiusCircular,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeText,
  },
});

interface Props {
  initialData: ApiPaginated<ServiceItem>;
  verticals: VerticalOption[];
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; serviceId: string | null } | null;

export function ServicesClient({ initialData, verticals }: Props) {
  const styles = useStyles();

  // Vertical filter lives in the URL so it survives refresh and is shareable
  // (deep-link: /catalog/services?vertical_id=…).
  const [verticalFilter, setVerticalFilter] = useQueryState("vertical_id");

  const extraFilters = useMemo<FilterCondition[] | undefined>(
    () =>
      verticalFilter
        ? [{ field: "vertical_id", operator: "eq", value: verticalFilter }]
        : undefined,
    [verticalFilter],
  );

  // Note: when `extraFilters` is set (a vertical is selected via deep-link),
  // useTableQuery intentionally ignores `initialData` and refetches once on
  // mount. The `data ?? initialData` fallback keeps the correct rows on screen
  // meanwhile, so this is a one-request cost on filtered deep-links, not a bug.
  const table = useTableQuery<ServiceItem>({
    queryKey: "catalog:services",
    fetcher: listServices,
    defaultSort: { field: "display_order", order: "asc" },
    searchFields: ["code", "name"],
    extraFilters,
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<ServiceItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const selectedVerticalName = useMemo(
    () => verticals.find((v) => v.id === verticalFilter)?.name ?? null,
    [verticals, verticalFilter],
  );

  const rowActions = useMemo<RowAction<ServiceItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (s) => setDrawer({ mode: "view", serviceId: s.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["SERVICES_UPDATE"],
        onSelect: (s) => setDrawer({ mode: "edit", serviceId: s.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["SERVICES_DELETE"],
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

  // When deep-linked to an inactive/stale vertical (not in the active list),
  // fall back to the name carried on the rows — every row shares the filter's
  // vertical — so the chip and dropdown never leak a raw UUID.
  const displayVerticalName = selectedVerticalName ?? data.data.items[0]?.vertical_name ?? null;

  const handleVerticalChange = (next: string | null) => {
    void setVerticalFilter(next);
    table.setPage(1);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteService(deleteTarget.id);
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
        <h1 className={styles.title}>Servicios</h1>
        <p className={styles.subtitle}>Gestiona las líneas de servicio dentro de cada vertical.</p>
      </header>

      <div className={styles.toolbar}>
        <Dropdown
          className={styles.verticalFilter}
          placeholder="Todas las verticales"
          value={displayVerticalName ?? ""}
          selectedOptions={verticalFilter ? [verticalFilter] : []}
          onOptionSelect={(_, d) => handleVerticalChange(d.optionValue || null)}
        >
          <Option value="">Todas las verticales</Option>
          {verticals.map((v) => (
            <Option key={v.id} value={v.id}>
              {v.name}
            </Option>
          ))}
        </Dropdown>
        <Input
          className={styles.search}
          placeholder="Buscar por código o nombre…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["SERVICES_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", serviceId: null })}
          >
            Nuevo servicio
          </Button>
        </PermissionGuard>
      </div>

      {verticalFilter ? (
        <div className={styles.chipRow}>
          <span className={styles.chip}>
            Vertical: {displayVerticalName ?? verticalFilter}
            <Button
              appearance="subtle"
              size="small"
              icon={<DismissRegular />}
              aria-label="Quitar filtro de vertical"
              onClick={() => handleVerticalChange(null)}
            />
          </span>
        </div>
      ) : null}

      <DataTable<ServiceItem>
        items={data.data.items}
        getRowKey={(s) => s.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0 || verticalFilter !== null}
        emptyTitle="Aún no hay servicios"
        emptyMessage="Crea el primero o elige otra vertical para empezar."
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
            key: "vertical_name",
            name: "Vertical",
            fieldName: "vertical_name",
            truncate: true,
            minWidth: 180,
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
            onRender: (s) => (
              <Badge appearance="filled" color={s.active ? "success" : "informative"}>
                {s.active ? "Activo" : "Deshabilitado"}
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
            onRender: (s) => formatDate(s.updated_on),
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
        <ServiceDrawer
          mode={drawer.mode}
          serviceId={drawer.serviceId}
          verticals={verticals}
          defaultVerticalId={verticalFilter}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar servicio?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el servicio "${deleteTarget.name}"? Los productos asociados se conservan. Podrás recrearlo más adelante.`
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
