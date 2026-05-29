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
import { useRouter } from "next/navigation";
import { useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { deleteOffice, listOffices } from "@/actions/office.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { BranchOption, OfficeItem } from "@/types/clinic.types";
import type { FilterCondition } from "@/types/query.types";

import { OfficeCreateDrawer } from "./OfficeCreateDrawer";

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
  branchFilter: { minWidth: "220px" },
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
  initialData: ApiPaginated<OfficeItem>;
  branches: BranchOption[];
}

export function OfficesClient({ initialData, branches }: Props) {
  const styles = useStyles();
  const router = useRouter();

  // Branch filter lives in the URL so it survives refresh and is shareable
  // (deep-link: /clinic/offices?branch_id=… — used by the branch list's
  // "Ver N consultorios" link).
  const [branchFilter, setBranchFilter] = useQueryState("branch_id");

  const extraFilters = useMemo<FilterCondition[] | undefined>(
    () =>
      branchFilter ? [{ field: "branch_id", operator: "eq", value: branchFilter }] : undefined,
    [branchFilter],
  );

  const table = useTableQuery<OfficeItem>({
    queryKey: "clinic:offices",
    fetcher: listOffices,
    defaultSort: { field: "name", order: "asc" },
    searchFields: ["code", "name"],
    extraFilters,
    initialData,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<OfficeItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const selectedBranchName = useMemo(
    () => branches.find((b) => b.id === branchFilter)?.name ?? null,
    [branches, branchFilter],
  );

  const data = table.query.data ?? initialData;

  // When deep-linked to an inactive/stale branch (not in the active list),
  // fall back to the name carried on the rows — every row shares the filter's
  // branch — so the chip and dropdown never leak a raw UUID.
  const displayBranchName = branchFilter
    ? (selectedBranchName ?? data.data.items[0]?.branch_name ?? null)
    : null;

  const rowActions = useMemo<RowAction<OfficeItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (o) => router.push(`/clinic/offices/${o.id}`),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["OFFICES_UPDATE"],
        onSelect: (o) => router.push(`/clinic/offices/${o.id}?tab=details`),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["OFFICES_DELETE"],
        danger: true,
        onSelect: (o) => {
          setDeleteError(null);
          setDeleteTarget(o);
        },
      },
    ],
    [router],
  );

  const handleBranchChange = (next: string | null) => {
    void setBranchFilter(next);
    table.setPage(1);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteOffice(deleteTarget.id);
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
        <h1 className={styles.title}>Consultorios</h1>
        <p className={styles.subtitle}>Gestiona los consultorios dentro de cada sede.</p>
      </header>

      <div className={styles.toolbar}>
        <Dropdown
          className={styles.branchFilter}
          placeholder="Todas las sedes"
          value={displayBranchName ?? ""}
          selectedOptions={branchFilter ? [branchFilter] : []}
          onOptionSelect={(_, d) => handleBranchChange(d.optionValue || null)}
        >
          <Option value="">Todas las sedes</Option>
          {branches.map((b) => (
            <Option key={b.id} value={b.id}>
              {b.name}
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
        <PermissionGuard anyOf={["OFFICES_CREATE"]}>
          <Button appearance="primary" icon={<AddRegular />} onClick={() => setCreateOpen(true)}>
            Nuevo consultorio
          </Button>
        </PermissionGuard>
      </div>

      {branchFilter ? (
        <div className={styles.chipRow}>
          <span className={styles.chip}>
            Sede: {displayBranchName ?? branchFilter}
            <Button
              appearance="subtle"
              size="small"
              icon={<DismissRegular />}
              aria-label="Quitar filtro de sede"
              onClick={() => handleBranchChange(null)}
            />
          </span>
        </div>
      ) : null}

      <DataTable<OfficeItem>
        items={data.data.items}
        getRowKey={(o) => o.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0 || branchFilter !== null}
        emptyTitle={
          branchFilter ? "Esta sede aún no tiene consultorios" : "Aún no hay consultorios"
        }
        emptyMessage={
          branchFilter
            ? "Crea el primero dentro de esta sede."
            : "Crea el primero dentro de una sede para empezar."
        }
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
            onRender: (o) => <RowActions item={o} actions={rowActions} />,
          },
          {
            key: "branch_name",
            name: "Sede",
            fieldName: "branch_name",
            isSortable: true,
            truncate: true,
            minWidth: 180,
          },
          {
            key: "code",
            name: "Código",
            fieldName: "code",
            isSortable: true,
            truncate: true,
            minWidth: 160,
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
            key: "floor",
            name: "Piso",
            minWidth: 90,
            onRender: (o) => o.floor ?? "—",
          },
          {
            key: "verticals_count",
            name: "Verticales",
            fieldName: "verticals_count",
            numeric: true,
            minWidth: 110,
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (o) => (
              <Badge appearance="filled" color={o.active ? "success" : "informative"}>
                {o.active ? "Activo" : "Deshabilitado"}
              </Badge>
            ),
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 180,
            onRender: (o) => formatDate(o.updated_on),
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

      {createOpen ? (
        <OfficeCreateDrawer
          branches={branches}
          defaultBranchId={branchFilter}
          onClose={() => setCreateOpen(false)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar consultorio?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el consultorio "${deleteTarget.name}"? Sus horarios y excepciones se conservan.`
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
