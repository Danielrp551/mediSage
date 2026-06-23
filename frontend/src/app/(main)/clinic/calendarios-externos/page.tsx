import { listActiveBranches } from "@/actions/branch.actions";
import { listConnections } from "@/actions/calendar.actions";
import { requirePermission } from "@/lib/auth/session";

import { CalendarConnectionsClient } from "./_components/CalendarConnectionsClient";

export const metadata = { title: "Calendarios externos" };

interface PageProps {
  // El callback público del backend hace 302 de vuelta con ?calendar_error=CODE si el OAuth
  // (o una acción posterior) falló; si fue OK, vuelve sin query. (return_to lo fijó el cliente
  // al iniciar el OAuth.)
  searchParams: Promise<{ calendar_error?: string }>;
}

export default async function ExternalCalendarsPage({ searchParams }: PageProps) {
  await requirePermission("CALENDAR_CONNECTIONS_READ");
  const sp = await searchParams;

  const [initialData, branches] = await Promise.all([
    listConnections({
      pagination: { skip: 0, limit: 25 }, // pocas conexiones (1-2 típico); una página basta
      sorting: { sort_by: "created_on", sort_order: "asc" },
      filters: null,
    }),
    listActiveBranches(), // dropdown de sede del mapeo
  ]);

  return (
    <CalendarConnectionsClient
      initialData={initialData}
      branches={branches}
      oauthError={sp.calendar_error ?? null}
    />
  );
}
