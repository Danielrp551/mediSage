import { listActiveAppointmentStatuses } from "@/actions/appointment-status.actions";
import { listAppointments } from "@/actions/appointment.actions";
import { listActiveBranches } from "@/actions/branch.actions";
import { listActiveDoctors } from "@/actions/doctor.actions";
import { listActiveProducts } from "@/actions/product.actions";
import { requirePermission } from "@/lib/auth/session";

import { AppointmentsClient } from "./_components/AppointmentsClient";

export const metadata = { title: "Citas" };

export default async function AppointmentsPage() {
  await requirePermission("APPOINTMENTS_READ");

  // Prefetch en paralelo (sin waterfall): la primera página de citas + las listas
  // /active que alimentan los dropdowns de filtro (doctor/estado/sede/producto).
  // El prefetch ordena por `scheduled_for asc` (columna REAL) y limit 10 → DEBE
  // coincidir con el defaultSort/defaultPageSize del cliente para usar initialData
  // sin refetch ni flash.
  const [initialData, doctors, statuses, branches, products] = await Promise.all([
    listAppointments({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "scheduled_for", sort_order: "asc" },
      filters: null,
    }),
    listActiveDoctors(),
    listActiveAppointmentStatuses(),
    listActiveBranches(),
    listActiveProducts(),
  ]);

  return (
    <AppointmentsClient
      initialData={initialData}
      doctors={doctors}
      statuses={statuses}
      branches={branches}
      products={products}
    />
  );
}
