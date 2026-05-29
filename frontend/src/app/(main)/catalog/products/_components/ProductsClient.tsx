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
  DeleteRegular,
  DismissRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useQueryState } from "nuqs";
import { useEffect, useMemo, useRef, useState } from "react";

import { deleteProduct, listProducts } from "@/actions/product.actions";
import { listActiveServices } from "@/actions/service.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { ProductItem, ServiceOption, VerticalOption } from "@/types/catalog.types";
import type { FilterCondition } from "@/types/query.types";

import { ProductDrawer } from "./ProductDrawer";

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
  filter: { minWidth: "200px" },
  search: { flex: 1, maxWidth: "320px" },
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
  initialData: ApiPaginated<ProductItem>;
  verticals: VerticalOption[];
  services: ServiceOption[];
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; productId: string | null } | null;

function formatPrice(amount: string, currency: string): string {
  const n = Number.parseFloat(amount);
  if (Number.isNaN(n)) return `${currency} ${amount}`;
  try {
    return new Intl.NumberFormat("es-PE", { style: "currency", currency }).format(n);
  } catch {
    return `${currency} ${amount}`;
  }
}

export function ProductsClient({ initialData, verticals, services }: Props) {
  const styles = useStyles();

  // Both filters live in the URL (deep-link + refresh friendly). Service is the
  // more specific filter; vertical falls back to the denormalized column.
  const [verticalFilter, setVerticalFilter] = useQueryState("vertical_id");
  const [serviceFilter, setServiceFilter] = useQueryState("service_id");

  // Service dropdown options follow the selected vertical. Seeded from the
  // server prefetch; reloaded when the vertical changes. The mount guard skips
  // the first run in production (the prefetch already matches the initial
  // vertical); under React Strict Mode a dev-only remount may refetch once —
  // harmless, the cancelled flag and matching response keep state correct.
  const [serviceOptions, setServiceOptions] = useState<ServiceOption[]>(services);
  const didMount = useRef(false);
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true;
      return;
    }
    let cancelled = false;
    void listActiveServices(verticalFilter ?? undefined).then((opts) => {
      if (!cancelled) setServiceOptions(opts);
    });
    return () => {
      cancelled = true;
    };
  }, [verticalFilter]);

  const extraFilters = useMemo<FilterCondition[] | undefined>(() => {
    if (serviceFilter) return [{ field: "service_id", operator: "eq", value: serviceFilter }];
    if (verticalFilter) return [{ field: "vertical_id", operator: "eq", value: verticalFilter }];
    return undefined;
  }, [serviceFilter, verticalFilter]);

  // Deep-linked filters make useTableQuery skip `initialData` and refetch once
  // on mount; the `data ?? initialData` fallback keeps rows on screen. Not a bug.
  const table = useTableQuery<ProductItem>({
    queryKey: "catalog:products",
    fetcher: listProducts,
    defaultSort: { field: "name", order: "asc" },
    searchFields: ["code", "name"],
    extraFilters,
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProductItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const data = table.query.data ?? initialData;

  // Resolve the filter's display name (fall back to a row's denormalized name
  // when a deep-linked id isn't in the active list). Null when no filter is
  // set, so the dropdown shows its placeholder instead of a stray row's name.
  const selectedVerticalName = verticalFilter
    ? (verticals.find((v) => v.id === verticalFilter)?.name ??
      data.data.items[0]?.vertical_name ??
      null)
    : null;
  const selectedServiceName = serviceFilter
    ? (serviceOptions.find((s) => s.id === serviceFilter)?.name ??
      data.data.items[0]?.service_name ??
      null)
    : null;

  const rowActions = useMemo<RowAction<ProductItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (p) => setDrawer({ mode: "view", productId: p.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["PRODUCTS_UPDATE"],
        onSelect: (p) => setDrawer({ mode: "edit", productId: p.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["PRODUCTS_DELETE"],
        danger: true,
        onSelect: (p) => {
          setDeleteError(null);
          setDeleteTarget(p);
        },
      },
    ],
    [],
  );

  const handleVerticalChange = (next: string | null) => {
    void setVerticalFilter(next);
    void setServiceFilter(null); // service depends on vertical — reset it
    table.setPage(1);
  };

  const handleServiceChange = (next: string | null) => {
    void setServiceFilter(next);
    table.setPage(1);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteProduct(deleteTarget.id);
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
        <h1 className={styles.title}>Productos</h1>
        <p className={styles.subtitle}>
          Gestiona los productos y servicios concretos que ofrece la clínica.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Dropdown
          className={styles.filter}
          placeholder="Todas las verticales"
          value={selectedVerticalName ?? ""}
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
        <Dropdown
          className={styles.filter}
          placeholder="Todos los servicios"
          value={selectedServiceName ?? ""}
          selectedOptions={serviceFilter ? [serviceFilter] : []}
          onOptionSelect={(_, d) => handleServiceChange(d.optionValue || null)}
        >
          <Option value="">Todos los servicios</Option>
          {serviceOptions.map((s) => (
            <Option key={s.id} value={s.id}>
              {s.name}
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
        <PermissionGuard anyOf={["PRODUCTS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", productId: null })}
          >
            Nuevo producto
          </Button>
        </PermissionGuard>
      </div>

      {verticalFilter || serviceFilter ? (
        <div className={styles.chipRow}>
          {verticalFilter ? (
            <span className={styles.chip}>
              Vertical: {selectedVerticalName ?? verticalFilter}
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de vertical"
                onClick={() => handleVerticalChange(null)}
              />
            </span>
          ) : null}
          {serviceFilter ? (
            <span className={styles.chip}>
              Servicio: {selectedServiceName ?? serviceFilter}
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de servicio"
                onClick={() => handleServiceChange(null)}
              />
            </span>
          ) : null}
        </div>
      ) : null}

      <DataTable<ProductItem>
        items={data.data.items}
        getRowKey={(p) => p.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0 || verticalFilter !== null || serviceFilter !== null}
        emptyTitle="Aún no hay productos"
        emptyMessage="Crea el primero o ajusta los filtros para empezar."
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
            onRender: (p) => <RowActions item={p} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Código",
            fieldName: "code",
            isSortable: true,
            truncate: true,
            minWidth: 170,
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
            key: "service_name",
            name: "Servicio",
            fieldName: "service_name",
            truncate: true,
            minWidth: 170,
          },
          {
            key: "vertical_name",
            name: "Vertical",
            fieldName: "vertical_name",
            truncate: true,
            minWidth: 150,
          },
          {
            key: "base_price",
            name: "Precio",
            align: "right",
            isSortable: true,
            minWidth: 120,
            onRender: (p) => formatPrice(p.base_price, p.currency),
          },
          {
            key: "requires_appointment",
            name: "Reserva",
            align: "center",
            minWidth: 110,
            onRender: (p) => (
              <Badge appearance="tint" color={p.requires_appointment ? "brand" : "informative"}>
                {p.requires_appointment ? "Agendable" : "Directo"}
              </Badge>
            ),
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (p) => (
              <Badge appearance="filled" color={p.active ? "success" : "informative"}>
                {p.active ? "Activo" : "Deshabilitado"}
              </Badge>
            ),
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 180,
            onRender: (p) => formatDate(p.updated_on),
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
        <ProductDrawer
          mode={drawer.mode}
          productId={drawer.productId}
          verticals={verticals}
          defaultVerticalId={verticalFilter}
          defaultServiceId={serviceFilter}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar producto?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el producto "${deleteTarget.name}"? Las citas y promociones históricas se conservan. Podrás recrearlo más adelante.`
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
