"use client";

import { Badge, Dropdown, Input, Option, makeStyles, tokens } from "@fluentui/react-components";
import { DismissRegular, SearchRegular } from "@fluentui/react-icons";
import { useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { listPromotionUsages } from "@/actions/promotion-usage.actions";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { useTableQuery } from "@/hooks/useTableQuery";
import { formatCurrency } from "@/lib/constants/marketing";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { PromotionOption, PromotionUsageItem } from "@/types/marketing.types";
import type { FilterCondition } from "@/types/query.types";

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
  filter: { minWidth: "220px" },
  amount: { fontVariantNumeric: "tabular-nums" },
  discount: { fontVariantNumeric: "tabular-nums", color: tokens.colorPaletteGreenForeground1 },
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
  clearChip: {
    border: "none",
    background: "transparent",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    padding: tokens.spacingHorizontalXXS,
    color: appTokens.chromeTextMuted,
  },
});

interface Props {
  initialData: ApiPaginated<PromotionUsageItem>;
  promotions: PromotionOption[];
  /** Nombre de la persona del deep-link `?person_id=`, resuelto server-side (null si no). */
  personName?: string | null;
}

/**
 * Formatea el instante de aplicación con TZ FIJA America/Lima → determinista entre SSR
 * (entorno UTC) y cliente (Lima) → sin mismatch de hidratación. `formatDate` (sin timeZone)
 * usaría la TZ del entorno y desfasaría la hora en el SSR (lección §5/§17).
 */
function formatAppliedAt(iso: string): string {
  return new Date(iso).toLocaleString("es-PE", {
    timeZone: "America/Lima",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PromotionUsagesClient({ initialData, promotions, personName }: Props) {
  const styles = useStyles();

  // Filtros deep-linkables sobre columnas REALES (ALLOWED_FIELDS de promotion_usage).
  const [promotionFilter, setPromotionFilter] = useQueryState("promotion_id");
  const [personFilter, setPersonFilter] = useQueryState("person_id");

  const extraFilters = useMemo<FilterCondition[] | undefined>(() => {
    const conds: FilterCondition[] = [];
    if (promotionFilter)
      conds.push({ field: "promotion_id", operator: "eq", value: promotionFilter });
    if (personFilter) conds.push({ field: "person_id", operator: "eq", value: personFilter });
    return conds.length > 0 ? conds : undefined;
  }, [promotionFilter, personFilter]);

  const table = useTableQuery<PromotionUsageItem>({
    queryKey: "marketing:promotion-usages",
    fetcher: listPromotionUsages,
    defaultSort: { field: "created_on", order: "desc" }, // columna real (= applied_at)
    extraFilters,
    initialData,
  });

  // Búsqueda por nombre = CLIENT-SIDE sobre la página visible: promotion/person/product
  // _name son denormalizados (NO whitelistados) → no se pueden filtrar server-side. Acota
  // las filas mostradas de la página actual; los filtros precisos son promo/persona.
  const [nameSearch, setNameSearch] = useState("");

  const data = table.query.data ?? initialData;
  const visibleItems = useMemo(() => {
    const q = nameSearch.trim().toLowerCase();
    if (!q) return data.data.items;
    return data.data.items.filter(
      (u) =>
        u.promotion_name.toLowerCase().includes(q) ||
        u.person_name.toLowerCase().includes(q) ||
        u.product_name.toLowerCase().includes(q),
    );
  }, [data.data.items, nameSearch]);

  const selectedPromotionName = promotionFilter
    ? (promotions.find((p) => p.id === promotionFilter)?.name ?? promotionFilter)
    : null;

  const handlePromotionChange = (next: string | null) => {
    void setPromotionFilter(next);
    table.setPage(1);
  };

  const hasFilter = promotionFilter !== null || personFilter !== null;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Usos de promoción</h1>
        <p className={styles.subtitle}>
          Historial de promociones aplicadas: producto, persona y montos descontados.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por promoción, persona o producto…"
          value={nameSearch}
          onChange={(_, d) => setNameSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <Dropdown
          className={styles.filter}
          placeholder="Todas las promociones"
          value={selectedPromotionName ?? ""}
          selectedOptions={promotionFilter ? [promotionFilter] : []}
          onOptionSelect={(_, d) => handlePromotionChange(d.optionValue || null)}
        >
          <Option value="">Todas las promociones</Option>
          {promotions.map((p) => (
            <Option key={p.id} value={p.id}>
              {p.name}
            </Option>
          ))}
        </Dropdown>
      </div>

      {hasFilter ? (
        <div className={styles.chipRow}>
          {promotionFilter ? (
            <span className={styles.chip}>
              Promoción: {selectedPromotionName}
              <button
                type="button"
                className={styles.clearChip}
                aria-label="Quitar filtro de promoción"
                onClick={() => handlePromotionChange(null)}
              >
                <DismissRegular />
              </button>
            </span>
          ) : null}
          {personFilter ? (
            <span className={styles.chip}>
              Persona: {personName ?? personFilter}
              <button
                type="button"
                className={styles.clearChip}
                aria-label="Quitar filtro de persona"
                onClick={() => {
                  void setPersonFilter(null);
                  table.setPage(1);
                }}
              >
                <DismissRegular />
              </button>
            </span>
          ) : null}
        </div>
      ) : null}

      <DataTable<PromotionUsageItem>
        items={visibleItems}
        getRowKey={(u) => u.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={hasFilter || nameSearch.length > 0}
        emptyTitle="Aún no hay usos de promoción registrados"
        emptyMessage="Las promociones aplicadas (al agendar una cita o desde el bot) aparecerán aquí."
        sortField={table.sortField}
        sortOrder={table.sortOrder}
        onSort={(field, descending) => table.setSort(field, descending ? "desc" : "asc")}
        columns={[
          {
            // Único sortable: created_on (= applied_at) es columna real (ALLOWED_FIELDS).
            key: "created_on",
            name: "Aplicado",
            isSortable: true,
            minWidth: 150,
            onRender: (u) => formatAppliedAt(u.created_on),
          },
          {
            key: "promotion_name",
            name: "Promoción",
            truncate: true,
            minWidth: 180,
            onRender: (u) => u.promotion_name,
          },
          {
            key: "person_name",
            name: "Persona",
            truncate: true,
            minWidth: 180,
            onRender: (u) => u.person_name,
          },
          {
            key: "product_name",
            name: "Producto",
            truncate: true,
            minWidth: 170,
            onRender: (u) => u.product_name,
          },
          {
            key: "original_amount",
            name: "Precio",
            align: "right",
            minWidth: 110,
            onRender: (u) => (
              <span className={styles.amount}>{formatCurrency(u.original_amount, u.currency)}</span>
            ),
          },
          {
            key: "discount_amount",
            name: "Descuento",
            align: "right",
            minWidth: 110,
            onRender: (u) => (
              <span className={styles.discount}>
                −{formatCurrency(u.discount_amount, u.currency)}
              </span>
            ),
          },
          {
            key: "final_amount",
            name: "Final",
            align: "right",
            minWidth: 110,
            onRender: (u) => (
              <span className={styles.amount}>{formatCurrency(u.final_amount, u.currency)}</span>
            ),
          },
          {
            key: "campaign_name",
            name: "Campaña",
            truncate: true,
            minWidth: 150,
            onRender: (u) => u.campaign_name ?? "—",
          },
          {
            key: "appointment_id",
            name: "Origen",
            align: "center",
            minWidth: 110,
            onRender: (u) =>
              u.appointment_id ? (
                <Badge appearance="tint" color="brand">
                  Con cita
                </Badge>
              ) : (
                <Badge appearance="tint" color="informative">
                  Sin cita
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
    </div>
  );
}
