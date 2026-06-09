import { listCampaigns } from "@/actions/campaign.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition } from "@/types/query.types";

import { CampaignsClient } from "./_components/CampaignsClient";

export const metadata = { title: "Campañas" };

interface PageProps {
  searchParams: Promise<{ status?: string }>;
}

export default async function CampaignsPage({ searchParams }: PageProps) {
  await requirePermission("CAMPAIGNS_READ");

  // Deep-link de estado: ?status=active filtra por la columna REAL `status`
  // (es columna de ALLOWED_FIELDS; los *_name denormalizados no lo son). Si no
  // hay `status` en la URL, no se arma filtro → el prefetch sirve a la query
  // default sin refetch.
  const sp = await searchParams;
  const conditions: FilterCondition[] = [];
  if (sp.status) {
    conditions.push({ field: "status", operator: "eq", value: sp.status });
  }
  const filters =
    conditions.length > 0 ? { filters: [{ operator: "AND" as const, conditions }] } : null;

  const [initialData, verticals] = await Promise.all([
    listCampaigns({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "created_on", sort_order: "desc" },
      filters,
    }),
    listActiveVerticals(),
  ]);

  return <CampaignsClient initialData={initialData} verticals={verticals} />;
}
