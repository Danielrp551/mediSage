import { listChannelAccounts } from "@/actions/channel-account.actions";
import { requirePermission } from "@/lib/auth/session";

import { ChannelAccountsClient } from "./_components/ChannelAccountsClient";

export const metadata = { title: "Canales" };

// Tamaño de la primera página: el client debe usar el MISMO defaultPageSize para
// que el footer no quede desincronizado (lección useTableQuery default=10).
const PAGE_SIZE = 10;

export default async function ChannelAccountsPage() {
  await requirePermission("CHANNEL_ACCOUNTS_READ");

  // defaultSort = columna REAL (created_on) — `name`/`channel_type` SÍ son reales
  // y server-sortables, pero el prefetch y el defaultSort del client DEBEN
  // coincidir para no provocar flash + refetch.
  const initialData = await listChannelAccounts({
    pagination: { skip: 0, limit: PAGE_SIZE },
    sorting: { sort_by: "created_on", sort_order: "desc" },
  });

  return <ChannelAccountsClient initialData={initialData} pageSize={PAGE_SIZE} />;
}
