import { getPerson } from "@/actions/person.actions";
import { listActivePromotions } from "@/actions/promotion.actions";
import { listPromotionUsages } from "@/actions/promotion-usage.actions";
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { PromotionUsagesClient } from "./_components/PromotionUsagesClient";

export const metadata = { title: "Usos de promoción" };

interface PageProps {
  searchParams: Promise<{ promotion_id?: string; person_id?: string }>;
}

/** Resuelve el nombre de la persona del deep-link para el chip (server-side; el filtro
 * por persona llega por link, no hay input en la UI). `null` si no se pudo resolver. */
async function resolvePersonName(personId: string | undefined): Promise<string | null> {
  if (!personId) return null;
  try {
    const res = await getPerson(personId);
    return res.data.full_name;
  } catch {
    return null; // persona inexistente/borrada → el chip cae al id
  }
}

export default async function PromotionUsagesPage({ searchParams }: PageProps) {
  await requirePermission("PROMOTION_USAGES_READ");
  const sp = await searchParams;

  // Deep-link → FilterCondition sobre columnas REALES (promotion_id/person_id están en
  // ALLOWED_FIELDS de promotion_usage; los *_name denormalizados NO).
  const conditions: FilterCondition[] = [];
  if (sp.promotion_id) {
    conditions.push({ field: "promotion_id", operator: "eq", value: sp.promotion_id });
  }
  if (sp.person_id) {
    conditions.push({ field: "person_id", operator: "eq", value: sp.person_id });
  }
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  const [initialData, promotions, personName] = await Promise.all([
    listPromotionUsages({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "created_on", sort_order: "desc" }, // columna real (= applied_at)
      filters,
    }),
    listActivePromotions(),
    resolvePersonName(sp.person_id),
  ]);

  return (
    <PromotionUsagesClient
      initialData={initialData}
      promotions={promotions}
      personName={personName}
    />
  );
}
