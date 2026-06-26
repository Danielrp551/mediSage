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

import { deleteDoctor, listDoctors } from "@/actions/doctor.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { VerticalOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import type { FilterCondition } from "@/types/query.types";
import type { DoctorItem } from "@/types/staff.types";

import { DoctorCreateDrawer } from "./DoctorCreateDrawer";

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
  initialData: ApiPaginated<DoctorItem>;
  branches: BranchOption[];
  verticals: VerticalOption[];
}

export function DoctorsClient({ initialData, branches, verticals }: Props) {
  const styles = useStyles();
  const router = useRouter();

  // Filtros en la URL: sobreviven refresh y son deep-linkables. branch_id /
  // vertical_id se traducen a un join EXISTS sobre el M:N por el backend.
  const [branchFilter, setBranchFilter] = useQueryState("branch_id");
  const [verticalFilter, setVerticalFilter] = useQueryState("vertical_id");

  const extraFilters = useMemo<FilterCondition[] | undefined>(() => {
    const conds: FilterCondition[] = [];
    if (branchFilter) conds.push({ field: "branch_id", operator: "eq", value: branchFilter });
    if (verticalFilter) conds.push({ field: "vertical_id", operator: "eq", value: verticalFilter });
    return conds.length > 0 ? conds : undefined;
  }, [branchFilter, verticalFilter]);

  // full_name/email NO son columnas de `doctor` (se denormalizan del User) → NO
  // están en DoctorRepository.ALLOWED_FIELDS, y el query builder responde 400 al
  // ordenar/filtrar por ellas (whitelist estricta, NO las ignora). Por eso:
  //  - el default sort usa `created_on` (columna real) — DEBE coincidir con el
  //    prefetch del page.tsx para que `initialData` se use sin refetch;
  //  - la búsqueda por nombre/correo/CMP es CLIENT-SIDE (`filteredItems`), sin
  //    `searchFields`;
  //  - las columnas full_name/email NO son ordenables (un click haría sort 400).
  // useTableQuery sigue manejando paginación / sort / extraFilters (branch_id /
  // vertical_id) server-side.
  const table = useTableQuery<DoctorItem>({
    queryKey: "staff:doctors",
    fetcher: listDoctors,
    defaultSort: { field: "created_on", order: "desc" },
    extraFilters,
    initialData,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DoctorItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  // Búsqueda por nombre/correo/CMP: client-side sobre la página cargada.
  const [searchText, setSearchText] = useState("");

  const data = table.query.data ?? initialData;

  const filteredItems = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    if (!needle) return data.data.items;
    return data.data.items.filter((d) =>
      [d.full_name, d.email, d.cmp_code].some((field) =>
        (field ?? "").toLowerCase().includes(needle),
      ),
    );
  }, [data.data.items, searchText]);

  const selectedBranchName = useMemo(
    () => branches.find((b) => b.id === branchFilter)?.name ?? null,
    [branches, branchFilter],
  );
  const selectedVerticalName = useMemo(
    () => verticals.find((v) => v.id === verticalFilter)?.name ?? null,
    [verticals, verticalFilter],
  );

  const rowActions = useMemo<RowAction<DoctorItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (d) => router.push(`/staff/doctors/${d.id}`),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["DOCTORS_UPDATE"],
        onSelect: (d) => router.push(`/staff/doctors/${d.id}?tab=profile`),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["DOCTORS_DELETE"],
        danger: true,
        onSelect: (d) => {
          setDeleteError(null);
          setDeleteTarget(d);
        },
      },
    ],
    [router],
  );

  const handleBranchChange = (next: string | null) => {
    void setBranchFilter(next);
    table.setPage(1);
  };
  const handleVerticalChange = (next: string | null) => {
    void setVerticalFilter(next);
    table.setPage(1);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteDoctor(deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  };

  const isFiltered =
    searchText.trim().length > 0 || branchFilter !== null || verticalFilter !== null;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Doctores</h1>
        <p className={styles.subtitle}>Gestiona los doctores y su perfil profesional.</p>
      </header>

      <div className={styles.toolbar}>
        <Dropdown
          className={styles.filter}
          placeholder="Todas las sedes"
          value={selectedBranchName ?? ""}
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
        <Input
          className={styles.search}
          placeholder="Buscar por nombre, correo o CMP…"
          value={searchText}
          onChange={(_, d) => setSearchText(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["DOCTORS_CREATE"]}>
          <Button appearance="primary" icon={<AddRegular />} onClick={() => setCreateOpen(true)}>
            Nuevo doctor
          </Button>
        </PermissionGuard>
      </div>

      {branchFilter || verticalFilter ? (
        <div className={styles.chipRow}>
          {branchFilter ? (
            <span className={styles.chip}>
              Sede: {selectedBranchName ?? branchFilter}
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de sede"
                onClick={() => handleBranchChange(null)}
              />
            </span>
          ) : null}
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
        </div>
      ) : null}

      <DataTable<DoctorItem>
        items={filteredItems}
        getRowKey={(d) => d.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={isFiltered}
        emptyTitle="Aún no hay doctores"
        emptyMessage="Crea el primer doctor para empezar."
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
            onRender: (d) => <RowActions item={d} actions={rowActions} />,
          },
          {
            // No isSortable: full_name no es columna de `doctor` (denormalizado
            // del User) → ordenar por ella es 400. Se busca client-side.
            key: "full_name",
            name: "Doctor",
            fieldName: "full_name",
            truncate: true,
            minWidth: 200,
          },
          {
            // No isSortable: email tampoco es columna server-ordenable.
            key: "email",
            name: "Correo",
            fieldName: "email",
            truncate: true,
            minWidth: 220,
          },
          {
            key: "cmp_code",
            name: "CMP",
            isSortable: true,
            minWidth: 120,
            onRender: (d) => d.cmp_code ?? "—",
          },
          {
            key: "slot_duration_min",
            name: "Slot",
            isSortable: true,
            minWidth: 90,
            onRender: (d) => `${d.slot_duration_min} min`,
          },
          {
            key: "branches_count",
            name: "Sedes",
            fieldName: "branches_count",
            numeric: true,
            minWidth: 90,
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
            onRender: (d) => (
              <Badge appearance="filled" color={d.active ? "success" : "informative"}>
                {d.active ? "Activo" : "Inactivo"}
              </Badge>
            ),
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 180,
            onRender: (d) => formatDate(d.updated_on),
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
        <DoctorCreateDrawer
          branches={branches}
          verticals={verticals}
          onClose={() => setCreateOpen(false)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar doctor?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el perfil del doctor "${deleteTarget.full_name}"? Se deshabilitará el perfil de doctor. El usuario asociado no se elimina.`
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
