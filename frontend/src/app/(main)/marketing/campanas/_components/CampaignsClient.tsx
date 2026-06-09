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
import { useMemo, useState } from "react";

import { deleteCampaign, listCampaigns } from "@/actions/campaign.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { CAMPAIGN_STATUS_META } from "@/lib/constants/marketing";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { VerticalOption } from "@/types/catalog.types";
import type { CampaignItem, CampaignStatus } from "@/types/marketing.types";
import { CAMPAIGN_STATUSES } from "@/types/marketing.types";
import type { FilterCondition } from "@/types/query.types";

import { CampaignDrawer } from "./CampaignDrawer";

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
  filter: { minWidth: "200px" },
  code: { fontFamily: tokens.fontFamilyMonospace },
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
  initialData: ApiPaginated<CampaignItem>;
  verticals: VerticalOption[];
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; campaignId: string | null } | null;

/** Badge de estado con color FIJO del front (ADR-013: enum cerrado, no catálogo). */
function StatusBadge({ status }: { status: CampaignStatus }) {
  const meta = CAMPAIGN_STATUS_META[status];
  return (
    <Badge
      appearance="filled"
      style={{ backgroundColor: meta.color, color: tokens.colorNeutralForegroundOnBrand }}
    >
      {meta.label}
    </Badge>
  );
}

/**
 * Formatea una fecha date-pura "YYYY-MM-DD" a "DD/MM/YYYY" SIN pasar por
 * `new Date(iso)` (que la interpretaría como medianoche UTC y desfasaría el día
 * en Lima, UTC-5). `null` → "—".
 */
function formatDateOnly(date: string | null): string {
  if (!date) return "—";
  const [y, m, d] = date.split("-");
  if (!y || !m || !d) return date;
  return `${d}/${m}/${y}`;
}

export function CampaignsClient({ initialData, verticals }: Props) {
  const styles = useStyles();

  // Filtro de estado en la URL (deep-linkable, sobrevive refresh). Mapea a la
  // columna REAL `status` (ALLOWED_FIELDS); `undefined` (no `[]`) cuando no hay
  // filtro → useTableQuery usa initialData sin refetch.
  const [statusFilter, setStatusFilter] = useQueryState("status");

  const extraFilters = useMemo<FilterCondition[] | undefined>(() => {
    if (!statusFilter) return undefined;
    return [{ field: "status", operator: "eq", value: statusFilter }];
  }, [statusFilter]);

  const table = useTableQuery<CampaignItem>({
    queryKey: "marketing:campaigns",
    fetcher: listCampaigns,
    defaultSort: { field: "created_on", order: "desc" },
    searchFields: ["code", "name"],
    extraFilters,
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<CampaignItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const selectedStatusLabel =
    statusFilter && CAMPAIGN_STATUSES.includes(statusFilter as CampaignStatus)
      ? CAMPAIGN_STATUS_META[statusFilter as CampaignStatus].label
      : null;

  const handleStatusChange = (next: string | null) => {
    void setStatusFilter(next);
    table.setPage(1);
  };

  const rowActions = useMemo<RowAction<CampaignItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (c) => setDrawer({ mode: "view", campaignId: c.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["CAMPAIGNS_UPDATE"],
        onSelect: (c) => setDrawer({ mode: "edit", campaignId: c.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["CAMPAIGNS_DELETE"],
        danger: true,
        onSelect: (c) => {
          setDeleteError(null);
          setDeleteTarget(c);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteCampaign(deleteTarget.id);
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
        <h1 className={styles.title}>Campañas</h1>
        <p className={styles.subtitle}>Organiza las campañas comerciales y su ciclo de vida.</p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por código o nombre…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <Dropdown
          className={styles.filter}
          placeholder="Todos los estados"
          value={selectedStatusLabel ?? ""}
          selectedOptions={statusFilter ? [statusFilter] : []}
          onOptionSelect={(_, d) => handleStatusChange(d.optionValue || null)}
        >
          <Option value="">Todos los estados</Option>
          {CAMPAIGN_STATUSES.map((s) => (
            <Option key={s} value={s}>
              {CAMPAIGN_STATUS_META[s].label}
            </Option>
          ))}
        </Dropdown>
        <PermissionGuard anyOf={["CAMPAIGNS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", campaignId: null })}
          >
            Nueva campaña
          </Button>
        </PermissionGuard>
      </div>

      {statusFilter ? (
        <div className={styles.chipRow}>
          <span className={styles.chip}>
            Filtrado por: {selectedStatusLabel ?? statusFilter}
            <Button
              appearance="subtle"
              size="small"
              icon={<DismissRegular />}
              aria-label="Quitar filtro de estado"
              onClick={() => handleStatusChange(null)}
            />
          </span>
        </div>
      ) : null}

      <DataTable<CampaignItem>
        items={data.data.items}
        getRowKey={(c) => c.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0 || statusFilter !== null}
        emptyTitle="Aún no hay campañas"
        emptyMessage="Crea la primera para empezar a organizar tus promociones."
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
            onRender: (c) => <RowActions item={c} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Código",
            isSortable: true,
            truncate: true,
            minWidth: 180,
            onRender: (c) => <span className={styles.code}>{c.code}</span>,
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
            key: "status",
            name: "Estado",
            isSortable: true,
            minWidth: 130,
            onRender: (c) => <StatusBadge status={c.status} />,
          },
          {
            // Denormalizado → NO ordenable (lección cd10c78). null = transversal.
            key: "target_vertical_name",
            name: "Vertical",
            truncate: true,
            minWidth: 160,
            onRender: (c) => c.target_vertical_name ?? "Transversal",
          },
          {
            // Denormalizado → NO ordenable. En F1 siempre 0 (M:N llega en F2).
            key: "promotions_count",
            name: "Promociones",
            align: "center",
            minWidth: 120,
            onRender: (c) => `${c.promotions_count} promos`,
          },
          {
            key: "start_date",
            name: "Inicio",
            isSortable: true,
            minWidth: 110,
            onRender: (c) => formatDateOnly(c.start_date),
          },
          {
            key: "end_date",
            name: "Fin",
            minWidth: 110,
            onRender: (c) => formatDateOnly(c.end_date),
          },
          {
            key: "active",
            name: "Habilitada",
            align: "center",
            minWidth: 110,
            onRender: (c) => (
              <Badge appearance="filled" color={c.active ? "success" : "informative"}>
                {c.active ? "Sí" : "No"}
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
        <CampaignDrawer
          mode={drawer.mode}
          campaignId={drawer.campaignId}
          verticals={verticals}
          onClose={() => setDrawer(null)}
          onChanged={() => void table.query.refetch()}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar campaña?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar la campaña "${deleteTarget.name}"? Esta acción la quita del listado; podrás recrearla más adelante.`
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
