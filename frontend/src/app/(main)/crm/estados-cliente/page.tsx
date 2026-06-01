import { listCustomerStatuses } from "@/actions/customer-status.actions";
import { requirePermission } from "@/lib/auth/session";

import { CustomerStatusesClient } from "./_components/CustomerStatusesClient";

export const metadata = { title: "Estados de cliente" };

export default async function CustomerStatusesPage() {
  await requirePermission("CUSTOMER_STATUSES_READ");
  const initialData = await listCustomerStatuses({
    pagination: { skip: 0, limit: 50 }, // catálogo chico; una sola página suele bastar
    sorting: { sort_by: "display_order", sort_order: "asc" }, // columna real
    filters: null,
  });
  return <CustomerStatusesClient initialData={initialData} />;
}
