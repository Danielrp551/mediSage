import { listMyLeads } from "@/actions/lead-assignment.actions";
import { requirePermission } from "@/lib/auth/session";

import { MyLeadsClient } from "./_components/MyLeadsClient";

export const metadata = { title: "Mis leads" };

export default async function MyLeadsPage() {
  await requirePermission("MY_LEADS_READ");

  // ⚠ defaultSort = `created_on` (NO `last_activity_at`): /me/leads ordena vía el
  // query de Person, cuyo ALLOWED_FIELDS NO incluye `last_activity_at`
  // (denormalizado → se ignoraría en silencio). `created_on` es columna real
  // sortable de Person. DEBE coincidir con el defaultSort del MyLeadsClient.
  const initialData = await listMyLeads({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "created_on", sort_order: "desc" },
    filters: null,
  });

  return <MyLeadsClient initialData={initialData} />;
}
