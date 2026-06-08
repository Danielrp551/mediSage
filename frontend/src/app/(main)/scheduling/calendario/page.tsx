import { listActiveAppointmentStatuses } from "@/actions/appointment-status.actions";
import { listActiveBranches } from "@/actions/branch.actions";
import { listActiveDoctors } from "@/actions/doctor.actions";
import { listActiveProducts } from "@/actions/product.actions";
import { requirePermission } from "@/lib/auth/session";

import { CalendarClient } from "./_components/CalendarClient";

export const metadata = { title: "Calendario" };

export default async function CalendarPage() {
  await requirePermission("APPOINTMENTS_READ");

  // Prefetch en paralelo (sin waterfall) de las listas /active que alimentan los
  // dropdowns del calendario (doctor/producto del modo semana; estado del modo día).
  // Las citas/​huecos las trae el cliente por rango (client-side, TZ-safe).
  const [doctors, products, branches, statuses] = await Promise.all([
    listActiveDoctors(),
    listActiveProducts(),
    listActiveBranches(),
    listActiveAppointmentStatuses(),
  ]);

  return (
    <CalendarClient doctors={doctors} products={products} branches={branches} statuses={statuses} />
  );
}
