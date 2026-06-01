import { listLeadStatuses } from "@/actions/lead-status.actions";
import { requirePermission } from "@/lib/auth/session";

import { LeadStatusesClient } from "./_components/LeadStatusesClient";

export const metadata = { title: "Estados de lead" };

export default async function LeadStatusesPage() {
  await requirePermission("LEAD_STATUSES_READ");
  const initialData = await listLeadStatuses({
    pagination: { skip: 0, limit: 50 }, // catálogo chico; una sola página suele bastar
    sorting: { sort_by: "display_order", sort_order: "asc" }, // columna real
    filters: null,
  });
  return <LeadStatusesClient initialData={initialData} />;
}
