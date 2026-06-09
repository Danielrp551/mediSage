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

import { deletePromotion, listPromotions } from "@/actions/promotion.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { formatDiscount } from "@/lib/constants/marketing";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { ProductOption } from "@/types/catalog.types";
import type { PromotionItem } from "@/types/marketing.types";

import { PromotionDrawer } from "./PromotionDrawer";

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
  code: { fontFamily: tokens.fontFamilyMonospace },
});

interface Props {
  initialData: ApiPaginated<PromotionItem>;
  products: ProductOption[];
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; promotionId: string | null } | null;

/**
 * Formatea una fecha date-pura "YYYY-MM-DD" a "DD/MM/YYYY" SIN pasar por
 * `new Date(iso)` (que la interpretaría como medianoche UTC y desfasaría el día
 * en Lima, UTC-5). `null` → "—". Espejo de `formatDateOnly` en CampaignsClient.
 */
function formatDateOnly(date: string | null): string {
  if (!date) return "—";
  const [y, m, d] = date.split("-");
  if (!y || !m || !d) return date;
  return `${d}/${m}/${y}`;
}

export function PromotionsClient({ initialData, products }: Props) {
  const styles = useStyles();

  const table = useTableQuery<PromotionItem>({
    queryKey: "marketing:promotions",
    fetcher: listPromotions,
    defaultSort: { field: "created_on", order: "desc" },
    searchFields: ["code", "name"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<PromotionItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<PromotionItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (p) => setDrawer({ mode: "view", promotionId: p.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["PROMOTIONS_UPDATE"],
        onSelect: (p) => setDrawer({ mode: "edit", promotionId: p.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["PROMOTIONS_DELETE"],
        danger: true,
        onSelect: (p) => {
          setDeleteError(null);
          setDeleteTarget(p);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deletePromotion(deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
      void table.query.refetch();
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  };

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Promociones</h1>
        <p className={styles.subtitle}>
          Define descuentos reutilizables y los productos a los que aplican.
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
        <PermissionGuard anyOf={["PROMOTIONS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", promotionId: null })}
          >
            Nueva promoción
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<PromotionItem>
        items={data.data.items}
        getRowKey={(p) => p.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay promociones"
        emptyMessage="Crea la primera para empezar a ofrecer descuentos."
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
            isSortable: true,
            truncate: true,
            minWidth: 180,
            onRender: (p) => <span className={styles.code}>{p.code}</span>,
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
            // Ordena por la columna REAL discount_type (ALLOWED_FIELDS). El texto
            // mostrado combina type + value + currency vía formatDiscount.
            key: "discount_type",
            name: "Descuento",
            isSortable: true,
            minWidth: 120,
            onRender: (p) =>
              formatDiscount({
                discount_type: p.discount_type,
                discount_value: p.discount_value,
                currency: p.currency,
              }),
          },
          {
            // Denormalizado (products_count) → NO ordenable (lección cd10c78).
            key: "coverage",
            name: "Cobertura",
            minWidth: 160,
            onRender: (p) =>
              p.applies_to_all_products ? (
                <Badge appearance="filled" color="brand">
                  Todos los productos
                </Badge>
              ) : (
                <Badge appearance="tint" color="informative">
                  {p.products_count} productos
                </Badge>
              ),
          },
          {
            // Denormalizado → NO ordenable.
            key: "campaigns_count",
            name: "Campañas",
            align: "center",
            minWidth: 110,
            onRender: (p) => `${p.campaigns_count} campañas`,
          },
          {
            key: "start_date",
            name: "Inicio",
            isSortable: true,
            minWidth: 110,
            onRender: (p) => formatDateOnly(p.start_date),
          },
          {
            key: "end_date",
            name: "Fin",
            isSortable: true,
            minWidth: 110,
            onRender: (p) => formatDateOnly(p.end_date),
          },
          {
            key: "max_uses_total",
            name: "Usos máx.",
            align: "center",
            minWidth: 110,
            onRender: (p) => (p.max_uses_total === null ? "Ilimitado" : String(p.max_uses_total)),
          },
          {
            key: "max_uses_per_person",
            name: "Por persona",
            align: "center",
            minWidth: 110,
            onRender: (p) =>
              p.max_uses_per_person === null ? "Ilimitado" : String(p.max_uses_per_person),
          },
          {
            key: "active",
            name: "Habilitada",
            isSortable: true,
            align: "center",
            minWidth: 110,
            onRender: (p) => (
              <Badge appearance="filled" color={p.active ? "success" : "informative"}>
                {p.active ? "Sí" : "No"}
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
        <PromotionDrawer
          mode={drawer.mode}
          promotionId={drawer.promotionId}
          products={products}
          onClose={() => setDrawer(null)}
          onChanged={() => void table.query.refetch()}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar promoción?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar la promoción "${deleteTarget.name}"? Esta acción la quita del listado; podrás recrearla más adelante.`
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
