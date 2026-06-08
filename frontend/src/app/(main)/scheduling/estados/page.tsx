import { listAppointmentStatuses } from "@/actions/appointment-status.actions";
import { requirePermission } from "@/lib/auth/session";

import { AppointmentStatusesClient } from "./_components/AppointmentStatusesClient";

export const metadata = { title: "Estados de cita" };

export default async function AppointmentStatusesPage() {
  await requirePermission("APPOINTMENT_STATUSES_READ");
  const initialData = await listAppointmentStatuses({
    pagination: { skip: 0, limit: 50 }, // catálogo chico; una sola página suele bastar
    sorting: { sort_by: "display_order", sort_order: "asc" }, // columna real
    filters: null,
  });
  return <AppointmentStatusesClient initialData={initialData} />;
}
