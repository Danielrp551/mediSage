import { listActiveChannelAccounts } from "@/actions/channel-account.actions";
import { listConversations } from "@/actions/conversation.actions";
import { requirePermission } from "@/lib/auth/session";

import { InboxShell } from "../_components/InboxShell";

export const metadata = { title: "Bandeja" };

// Tamaño de la primera página del inbox. El client debe usar el MISMO
// defaultPageSize para que el footer/lista no quede desincronizado (lección
// useTableQuery default=10 → flash + refetch). El inbox carga un lote más grande
// (50) porque la búsqueda por nombre/identificador es client-side sobre la página.
const PAGE_SIZE = 50;

interface PageProps {
  searchParams: Promise<{ status?: string; channel_account_id?: string; c?: string }>;
}

export default async function InboxPage({ searchParams }: PageProps) {
  await requirePermission("CONVERSATIONS_READ");
  const { status, channel_account_id, c } = await searchParams;

  // Filtros deep-link → query params (NO body): el backend filtra por columnas
  // REALES (status / channel_account_id). El default del listado es status=open
  // (espeja el preset "Abiertas" del client) para no traer cerradas de entrada.
  const queryParams = new URLSearchParams();
  queryParams.set("status", status ?? "open");
  if (channel_account_id) queryParams.set("channel_account_id", channel_account_id);

  // Prefetch en paralelo: primera página del inbox + opciones de canal (filtro).
  const [initialData, channelAccounts] = await Promise.all([
    listConversations(
      {
        pagination: { skip: 0, limit: PAGE_SIZE },
        // defaultSort = columna REAL (last_message_at) — DEBE coincidir con el
        // defaultSort del client (lección desync footer / cd10c78).
        sorting: { sort_by: "last_message_at", sort_order: "desc" },
        filters: null,
      },
      queryParams.toString(),
    ).catch(() => null),
    listActiveChannelAccounts().catch(
      () => [] as Awaited<ReturnType<typeof listActiveChannelAccounts>>,
    ),
  ]);

  return (
    <InboxShell
      scope="all"
      initialData={initialData}
      initialQueryParams={queryParams.toString()}
      channelAccounts={channelAccounts}
      initialStatus={status ?? "open"}
      initialSelectedId={c ?? null}
      pageSize={PAGE_SIZE}
    />
  );
}
