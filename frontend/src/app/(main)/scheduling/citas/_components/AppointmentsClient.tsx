"use client";

import { Badge, Button, Dropdown, Option, makeStyles, tokens } from "@fluentui/react-components";
import { AddRegular, DismissRegular } from "@fluentui/react-icons";
import { useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { listAppointments } from "@/actions/appointment.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { ProductOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import type { FilterCondition } from "@/types/query.types";
import type { DoctorOption } from "@/types/staff.types";
import type { AppointmentItem, AppointmentStatusOption } from "@/types/scheduling.types";

import { AppointmentDetailDrawer } from "./AppointmentDetailDrawer";
import { BookingWizard } from "./BookingWizard";

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
  spacer: { flex: 1 },
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
  initialData: ApiPaginated<AppointmentItem>;
  doctors: DoctorOption[];
  statuses: AppointmentStatusOption[];
  branches: BranchOption[];
  products: ProductOption[];
}

export function AppointmentsClient({ initialData, doctors, statuses, branches, products }: Props) {
  const styles = useStyles();

  // Filtros en la URL: deep-linkables y sobreviven al refresh. Se mapean a
  // columnas REALES de Appointment (doctor_id/status_id/branch_id/product_id) —
  // NINGÚN *_name está en ALLOWED_FIELDS, así que el filtro va por el id (lección
  // cd10c78: filtrar/ordenar por denormalizado responde 400).
  const [doctorFilter, setDoctorFilter] = useQueryState("doctor_id");
  const [statusFilter, setStatusFilter] = useQueryState("status_id");
  const [branchFilter, setBranchFilter] = useQueryState("branch_id");
  const [productFilter, setProductFilter] = useQueryState("product_id");

  const extraFilters = useMemo<FilterCondition[] | undefined>(() => {
    const conds: FilterCondition[] = [];
    if (doctorFilter) conds.push({ field: "doctor_id", operator: "eq", value: doctorFilter });
    if (statusFilter) conds.push({ field: "status_id", operator: "eq", value: statusFilter });
    if (branchFilter) conds.push({ field: "branch_id", operator: "eq", value: branchFilter });
    if (productFilter) conds.push({ field: "product_id", operator: "eq", value: productFilter });
    // `undefined` (no `[]`) cuando no hay filtros → useTableQuery usa initialData
    // sin refetch (con un array vacío lo trataría como query no-default).
    return conds.length > 0 ? conds : undefined;
  }, [doctorFilter, statusFilter, branchFilter, productFilter]);

  // defaultSort = scheduled_for asc (columna REAL de ALLOWED_FIELDS) → coincide con
  // el prefetch del page.tsx para que initialData se use sin refetch.
  const table = useTableQuery<AppointmentItem>({
    queryKey: "scheduling:appointments",
    fetcher: listAppointments,
    defaultSort: { field: "scheduled_for", order: "asc" },
    defaultPageSize: 10,
    extraFilters,
    initialData,
  });

  const [wizardOpen, setWizardOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const data = table.query.data ?? initialData;

  const selectedDoctorName = useMemo(
    () => doctors.find((d) => d.id === doctorFilter)?.full_name ?? null,
    [doctors, doctorFilter],
  );
  const selectedStatusName = useMemo(
    () => statuses.find((s) => s.id === statusFilter)?.name ?? null,
    [statuses, statusFilter],
  );
  const selectedBranchName = useMemo(
    () => branches.find((b) => b.id === branchFilter)?.name ?? null,
    [branches, branchFilter],
  );
  const selectedProductName = useMemo(
    () => products.find((p) => p.id === productFilter)?.name ?? null,
    [products, productFilter],
  );

  // Cada cambio de filtro vuelve a la página 1 (un filtro nuevo puede recortar el
  // total por debajo de la página actual).
  const handleDoctorChange = (next: string | null) => {
    void setDoctorFilter(next);
    table.setPage(1);
  };
  const handleStatusChange = (next: string | null) => {
    void setStatusFilter(next);
    table.setPage(1);
  };
  const handleBranchChange = (next: string | null) => {
    void setBranchFilter(next);
    table.setPage(1);
  };
  const handleProductChange = (next: string | null) => {
    void setProductFilter(next);
    table.setPage(1);
  };

  const isFiltered =
    doctorFilter !== null ||
    statusFilter !== null ||
    branchFilter !== null ||
    productFilter !== null;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Citas</h1>
        <p className={styles.subtitle}>Agenda y reserva las citas de los pacientes.</p>
      </header>

      <div className={styles.toolbar}>
        <Dropdown
          className={styles.filter}
          placeholder="Todos los doctores"
          value={selectedDoctorName ?? ""}
          selectedOptions={doctorFilter ? [doctorFilter] : []}
          onOptionSelect={(_, d) => handleDoctorChange(d.optionValue || null)}
        >
          <Option value="">Todos los doctores</Option>
          {doctors.map((d) => (
            <Option key={d.id} value={d.id}>
              {d.full_name}
            </Option>
          ))}
        </Dropdown>
        <Dropdown
          className={styles.filter}
          placeholder="Todos los estados"
          value={selectedStatusName ?? ""}
          selectedOptions={statusFilter ? [statusFilter] : []}
          onOptionSelect={(_, d) => handleStatusChange(d.optionValue || null)}
        >
          <Option value="">Todos los estados</Option>
          {statuses.map((s) => (
            <Option key={s.id} value={s.id}>
              {s.name}
            </Option>
          ))}
        </Dropdown>
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
          placeholder="Todos los productos"
          value={selectedProductName ?? ""}
          selectedOptions={productFilter ? [productFilter] : []}
          onOptionSelect={(_, d) => handleProductChange(d.optionValue || null)}
        >
          <Option value="">Todos los productos</Option>
          {products.map((p) => (
            <Option key={p.id} value={p.id}>
              {p.name}
            </Option>
          ))}
        </Dropdown>
        <span className={styles.spacer} />
        <PermissionGuard anyOf={["APPOINTMENTS_CREATE"]}>
          <Button appearance="primary" icon={<AddRegular />} onClick={() => setWizardOpen(true)}>
            Nueva cita
          </Button>
        </PermissionGuard>
      </div>

      {isFiltered ? (
        <div className={styles.chipRow}>
          {doctorFilter ? (
            <span className={styles.chip}>
              Doctor: {selectedDoctorName ?? doctorFilter}
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de doctor"
                onClick={() => handleDoctorChange(null)}
              />
            </span>
          ) : null}
          {statusFilter ? (
            <span className={styles.chip}>
              Estado: {selectedStatusName ?? statusFilter}
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de estado"
                onClick={() => handleStatusChange(null)}
              />
            </span>
          ) : null}
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
          {productFilter ? (
            <span className={styles.chip}>
              Producto: {selectedProductName ?? productFilter}
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de producto"
                onClick={() => handleProductChange(null)}
              />
            </span>
          ) : null}
        </div>
      ) : null}

      <DataTable<AppointmentItem>
        items={data.data.items}
        getRowKey={(a) => a.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={isFiltered}
        emptyTitle="Aún no hay citas"
        emptyMessage="Reserva la primera cita con el botón “Nueva cita”."
        onRowClick={(a) => setDetailId(a.id)}
        sortField={table.sortField}
        sortOrder={table.sortOrder}
        onSort={(field, descending) => table.setSort(field, descending ? "desc" : "asc")}
        columns={[
          {
            // scheduled_for SÍ es columna real (ALLOWED_FIELDS) → ordenable + default sort.
            key: "scheduled_for",
            name: "Fecha y hora",
            isSortable: true,
            minWidth: 170,
            onRender: (a) => formatDate(a.scheduled_for),
          },
          {
            // person_name/doctor_name/… son denormalizados → NO ordenables (sort 400).
            key: "person_name",
            name: "Paciente",
            fieldName: "person_name",
            truncate: true,
            minWidth: 180,
          },
          {
            key: "doctor_name",
            name: "Doctor",
            fieldName: "doctor_name",
            truncate: true,
            minWidth: 180,
          },
          {
            key: "product_name",
            name: "Producto",
            fieldName: "product_name",
            truncate: true,
            minWidth: 160,
          },
          {
            key: "office",
            name: "Consultorio",
            truncate: true,
            minWidth: 200,
            onRender: (a) => `${a.office_name} · ${a.branch_name}`,
          },
          {
            key: "duration_min",
            name: "Duración",
            numeric: true,
            minWidth: 100,
            onRender: (a) => `${a.duration_min} min`,
          },
          {
            key: "status",
            name: "Estado",
            minWidth: 140,
            onRender: (a) => (
              <Badge
                appearance="filled"
                style={{
                  backgroundColor: a.status.color ?? tokens.colorNeutralBackground3,
                  color: tokens.colorNeutralForegroundOnBrand,
                }}
              >
                {a.status.name}
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

      {wizardOpen ? (
        <BookingWizard
          doctors={doctors}
          products={products}
          branches={branches}
          onClose={() => setWizardOpen(false)}
          onCreated={() => {
            void table.query.refetch();
            setWizardOpen(false);
          }}
        />
      ) : null}

      {detailId ? (
        <AppointmentDetailDrawer
          appointmentId={detailId}
          onClose={() => setDetailId(null)}
          onChanged={() => void table.query.refetch()}
          doctors={doctors}
          branches={branches}
          products={products}
        />
      ) : null}
    </div>
  );
}
