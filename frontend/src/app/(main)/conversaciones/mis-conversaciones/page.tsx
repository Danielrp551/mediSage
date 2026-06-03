import { listActiveChannelAccounts } from "@/actions/channel-account.actions";
import { listMyConversations } from "@/actions/conversation.actions";
import { requirePermission } from "@/lib/auth/session";

import { InboxShell } from "../_components/InboxShell";

export const metadata = { title: "Mi bandeja" };

// Mismo tamaño de página que la bandeja global (búsqueda client-side sobre la
// página visible) — el client usa el MISMO defaultPageSize para no desincronizar.
const PAGE_SIZE = 50;

interface PageProps {
  searchParams: Promise<{ status?: string; channel_account_id?: string; c?: string }>;
}

/**
 * "Mi bandeja": espejo de `bandeja` pero acotado al asesor logueado (el backend
 * resuelve assignee_user_id = actor del token). scope="mine" → InboxShell usa
 * `listMyConversations` para el prefetch y el polling. El default sigue siendo
 * status=open (preset "Abiertas").
 */
export default async function MyConversationsPage({ searchParams }: PageProps) {
  await requirePermission("MY_CONVERSATIONS_READ");
  const { status, channel_account_id, c } = await searchParams;

  // Filtros deep-link → query params (NO body). En "mine" solo aplican estado/canal
  // (las conversaciones ya están asignadas al actor server-side).
  const queryParams = new URLSearchParams();
  queryParams.set("status", status ?? "open");
  if (channel_account_id) queryParams.set("channel_account_id", channel_account_id);

  // Prefetch en paralelo: primera página de MI bandeja + opciones de canal (filtro).
  const [initialData, channelAccounts] = await Promise.all([
    listMyConversations(
      {
        pagination: { skip: 0, limit: PAGE_SIZE },
        // defaultSort = columna REAL (last_message_at) — coincide con el client.
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
      scope="mine"
      initialData={initialData}
      initialQueryParams={queryParams.toString()}
      channelAccounts={channelAccounts}
      initialStatus={status ?? "open"}
      initialSelectedId={c ?? null}
      pageSize={PAGE_SIZE}
    />
  );
}
